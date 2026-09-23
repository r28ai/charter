#!/usr/bin/env python
"""Drive every GitHub tool against the real API, with hardcoded arguments.

Deliberately not a test, for the same reason as ``live_google_check.py``: the
suite is offline by rule, and that rule is worth more than the convenience of
folding this in beside it. What the tests prove is that the pack is
self-consistent — that its schemas build, that its bytes are the ones it means
to send, that its handlers survive the payloads it was written against. What
this proves is that GitHub agrees, which no ``respx`` route can tell you.

No model is involved. Every argument below is written out by hand, so a run
costs GitHub API quota and nothing else.

    export GITHUB_TOKEN=$(gh auth token)
    uv run python scripts/live_github_check.py

Everything that writes goes to one sandbox repository, given by
``CHARTER_LIVE_REPO`` and defaulting to the repository that already exists for
this purpose. The run seeds what it needs — a branch, an issue, a pull request,
a workflow, a release — and tears it down at the end, including after a failure.

Four tools are **not** run, and are reported as skipped rather than quietly
left out:

``notifications_mark_read``
    Marks the authenticated user's entire inbox read. Account-wide, irreversible,
    and nothing to do with the sandbox.
``notifications_mark_thread_read``
    The same, one thread at a time, against real notifications.
``repos_create_fork``
    Creates a real repository. Deleting it again needs ``delete_repo``, which
    this token deliberately does not have, so a run would leave litter behind.
``actions_review_pending_deployments``
    Approves or rejects a deployment. Needs an environment with a protection
    rule and a run waiting on it, which is a fixture this script will not build
    in someone's account.

Nothing here prints a token, and the only thing it writes to is the sandbox.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from charter.auth import StaticTokenProvider
from charter.packs import github
from charter.types.errors import APIError, CharterError

REPO = os.environ.get("CHARTER_LIVE_REPO", "nqme-archive/harness-sandbox")
OWNER, _, NAME = REPO.partition("/")

# One suffix per run, so a failed run's leftovers never collide with the next.
RUN = f"charter-live-{int(time.time())}"

SKIPPED: Dict[str, str] = {
    "notifications_mark_read": "marks the whole inbox read; account-wide and irreversible",
    "notifications_mark_thread_read": "mutates a real notification thread",
    "repos_create_fork": "creates a repository this token cannot delete again",
    "actions_review_pending_deployments": "needs a protected environment awaiting review",
    "dependabot_update_alert": "needs a real Dependabot alert; the sandbox has none to dismiss",
}


# -----------------------------------------------------
# The runner
# -----------------------------------------------------


@dataclass
class Outcome:
    tool: str
    status: str  # pass | fail | skip | expected
    detail: str = ""


@dataclass
class Run:
    outcomes: List[Outcome] = field(default_factory=list)
    # Ids the earlier steps produced and the later ones need. The whole reason
    # this is a script with an order rather than a table of independent calls.
    state: Dict[str, Any] = field(default_factory=dict)

    async def call(
        self,
        tool_name: str,
        *,
        expect: Optional[Callable[[Any], bool]] = None,
        allow_status: tuple = (),
        note: str = "",
        **kwargs: Any,
    ) -> Any:
        """Invoke one tool and record what happened.

        ``allow_status`` names the HTTP statuses that are a *correct* answer for
        this repository rather than a failure — a 404 from
        ``repos_get_branch_protection`` on an unprotected branch is the endpoint
        working. Anything else is a fault and is reported as one.
        """
        tool = getattr(github, tool_name)
        try:
            result = await tool.ainvoke(**kwargs)
        except APIError as exc:
            status = getattr(exc, "status_code", None)
            if status in allow_status:
                self.outcomes.append(
                    Outcome(
                        tool_name,
                        "expected",
                        f"HTTP {status} — {note or 'documented for this repo'}",
                    )
                )
                return None
            self.outcomes.append(Outcome(tool_name, "fail", f"HTTP {status}: {str(exc)[:200]}"))
            return None
        except CharterError as exc:
            self.outcomes.append(
                Outcome(tool_name, "fail", f"{type(exc).__name__}: {str(exc)[:200]}")
            )
            return None
        except Exception as exc:  # noqa: BLE001 - a bug here is still a result
            self.outcomes.append(
                Outcome(tool_name, "fail", f"{type(exc).__name__}: {str(exc)[:200]}")
            )
            return None

        if expect is not None:
            try:
                ok = expect(result)
            except Exception as exc:  # noqa: BLE001
                self.outcomes.append(
                    Outcome(tool_name, "fail", f"check raised {type(exc).__name__}: {exc}")
                )
                return result
            if not ok:
                self.outcomes.append(
                    Outcome(tool_name, "fail", f"answered, but not as expected: {_brief(result)}")
                )
                return result

        self.outcomes.append(Outcome(tool_name, "pass", note or _brief(result)))
        return result

    def skip(self, tool_name: str, why: str) -> None:
        self.outcomes.append(Outcome(tool_name, "skip", why))


def _brief(value: Any, limit: int = 110) -> str:
    text = json.dumps(value, default=str) if not isinstance(value, str) else value
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit] + "…"


def repo_args() -> Dict[str, str]:
    return {"owner": OWNER, "repo": NAME}


# -----------------------------------------------------
# Phase 1 — the account, the quota, and reading a repository
# -----------------------------------------------------


async def phase_reads(run: Run) -> None:
    me = await run.call("users_get_authenticated", expect=lambda r: bool(r.get("login")))
    if me:
        run.state["login"] = me["login"]

    await run.call("rate_limit_get", expect=lambda r: r.get("core", {}).get("limit", 0) > 0)

    await run.call(
        "repos_get", **repo_args(), expect=lambda r: r["full_name"].lower() == REPO.lower()
    )
    await run.call(
        "repos_list_for_authenticated_user", per_page=5, expect=lambda r: isinstance(r, list)
    )
    await run.call(
        "repos_list_for_org",
        org=OWNER,
        per_page=5,
        allow_status=(404,),
        note=f"{OWNER} is a user account, not an organization",
    )
    await run.call("repos_get_readme", **repo_args(), expect=lambda r: "content" in r)
    await run.call(
        "repos_get_content",
        **repo_args(),
        path="README.md",
        expect=lambda r: isinstance(r.get("content"), str),
    )
    await run.call("repos_list_languages", **repo_args(), expect=lambda r: isinstance(r, dict))
    await run.call(
        "repos_list_contributors", **repo_args(), expect=lambda r: isinstance(r, (list, dict))
    )
    await run.call("repos_list_tags", **repo_args(), expect=lambda r: isinstance(r, list))
    await run.call(
        "branches_list", **repo_args(), expect=lambda r: any(b["name"] == "main" for b in r)
    )
    await run.call(
        "repos_get_branch", **repo_args(), branch="main", expect=lambda r: r["name"] == "main"
    )
    await run.call(
        "repos_get_branch_protection",
        **repo_args(),
        branch="main",
        allow_status=(403, 404),
        note="the sandbox's main branch is unprotected",
    )

    commits = await run.call(
        "repos_list_commits", **repo_args(), per_page=3, expect=lambda r: len(r) >= 1
    )
    if commits:
        run.state["head_sha"] = commits[0]["sha"]
        await run.call(
            "repos_get_commit",
            **repo_args(),
            ref=commits[0]["sha"],
            expect=lambda r: r.get("sha") == commits[0]["sha"],
        )
        await run.call(
            "repos_list_branches_for_head_commit",
            **repo_args(),
            commit_sha=commits[0]["sha"],
            expect=lambda r: isinstance(r, list),
        )
        await run.call(
            "repos_get_combined_status",
            **repo_args(),
            ref=commits[0]["sha"],
            expect=lambda r: r.get("state") in {"success", "pending", "failure", "error"},
        )
        await run.call(
            "checks_list_for_ref",
            **repo_args(),
            ref=commits[0]["sha"],
            expect=lambda r: "check_runs" in r,
        )
        await run.call(
            "checks_list_suites_for_ref",
            **repo_args(),
            ref=commits[0]["sha"],
            expect=lambda r: "check_suites" in r,
        )


# -----------------------------------------------------
# Phase 2 — the Git object store: one commit across two files
# -----------------------------------------------------


async def phase_git(run: Run) -> None:
    """The sequence the pack exists to make possible, run for real.

    A blob, a tree on top of the current one, a commit, a branch pointed at it —
    two files changed and one commit, where `repos_create_or_update_file` would
    have produced two.
    """
    head = await run.call(
        "git_refs_get",
        **repo_args(),
        ref="heads/main",
        expect=lambda r: len(r.get("sha", "")) == 40,
    )
    if not head:
        return
    base_sha = head["sha"]

    commit = await run.call(
        "git_commits_get",
        **repo_args(),
        commit_sha=base_sha,
        expect=lambda r: bool(r.get("tree")),
    )
    if not commit:
        return
    base_tree = commit["tree"]

    await run.call(
        "git_trees_get",
        **repo_args(),
        tree_sha=base_tree,
        recursive="1",
        expect=lambda r: "truncated" in r and isinstance(r.get("tree"), list),
    )

    blob = await run.call(
        "git_blobs_create",
        **repo_args(),
        content="written by the live check\n",
        expect=lambda r: len(r.get("sha", "")) == 40,
    )
    if blob:
        await run.call(
            "git_blobs_get",
            **repo_args(),
            file_sha=blob["sha"],
            expect=lambda r: r.get("content") == "written by the live check\n",
        )

    tree = await run.call(
        "git_trees_create",
        **repo_args(),
        base_tree=base_tree,
        tree=[
            {"path": f"{RUN}/one.txt", "mode": "100644", "type": "blob", "content": "one\n"},
            {
                "path": f"{RUN}/two.txt",
                "mode": "100644",
                "type": "blob",
                "sha": blob["sha"] if blob else None,
            },
        ]
        if blob
        else [
            {"path": f"{RUN}/one.txt", "mode": "100644", "type": "blob", "content": "one\n"},
        ],
        expect=lambda r: len(r.get("sha", "")) == 40,
    )
    if not tree:
        return

    made = await run.call(
        "git_commits_create",
        **repo_args(),
        message=f"{RUN}: two files, one commit",
        tree=tree["sha"],
        parents=[base_sha],
        expect=lambda r: len(r.get("sha", "")) == 40,
    )
    if not made:
        return
    run.state["commit_sha"] = made["sha"]

    branch = f"{RUN}-work"
    run.state["branch"] = branch
    await run.call(
        "git_refs_create",
        **repo_args(),
        ref=f"refs/heads/{branch}",
        sha=made["sha"],
        note=f"created {branch}",
    )
    await run.call(
        "git_refs_list_matching",
        **repo_args(),
        ref=f"heads/{RUN}",
        expect=lambda r: any(item["ref"].endswith(branch) for item in r),
    )

    # A second commit, so the branch has somewhere to move to.
    second_tree = await run.call(
        "git_trees_create",
        **repo_args(),
        base_tree=tree["sha"],
        tree=[
            {"path": f"{RUN}/one.txt", "mode": "100644", "type": "blob", "content": "one, edited\n"}
        ],
        expect=lambda r: bool(r.get("sha")),
    )
    if second_tree:
        second = await run.call(
            "git_commits_create",
            **repo_args(),
            message=f"{RUN}: edit one.txt",
            tree=second_tree["sha"],
            parents=[made["sha"]],
            expect=lambda r: bool(r.get("sha")),
        )
        if second:
            await run.call(
                "git_refs_update",
                **repo_args(),
                ref=f"heads/{branch}",
                sha=second["sha"],
                expect=lambda r: r.get("sha") == second["sha"],
            )
            run.state["commit_sha"] = second["sha"]

    await run.call(
        "repos_compare_commits",
        **repo_args(),
        basehead=f"main...{branch}",
        expect=lambda r: r.get("status") in {"ahead", "diverged"} and r.get("ahead_by", 0) >= 1,
    )

    tag_object = await run.call(
        "git_tags_create",
        **repo_args(),
        tag=f"{RUN}-v1",
        message="live check tag",
        object=run.state["commit_sha"],
        type="commit",
        expect=lambda r: bool(r.get("sha")),
    )
    if tag_object:
        await run.call(
            "git_refs_create",
            **repo_args(),
            ref=f"refs/tags/{RUN}-v1",
            sha=tag_object["sha"],
            note="the annotated tag's reference, which the tag object is not",
        )
        run.state["tag"] = f"{RUN}-v1"

    # The one-file-per-commit path, and its delete, on their own branch.
    written = await run.call(
        "repos_create_or_update_file",
        **repo_args(),
        path=f"{RUN}/scratch.txt",
        message=f"{RUN}: add scratch.txt",
        content="delete me\n",
        branch=branch,
        expect=lambda r: bool(r.get("content", {}).get("sha")),
    )
    if written:
        await run.call(
            "repos_delete_file",
            **repo_args(),
            path=f"{RUN}/scratch.txt",
            message=f"{RUN}: remove scratch.txt",
            sha=written["content"]["sha"],
            branch=branch,
            expect=lambda r: bool(r.get("commit", {}).get("sha")),
        )

    # A branch to rename and then merge, so neither test touches the work branch.
    spare = f"{RUN}-spare"
    if (
        await run.call(
            "git_refs_create",
            **repo_args(),
            ref=f"refs/heads/{spare}",
            sha=base_sha,
            note=f"created {spare}",
        )
        is not None
    ):
        renamed = f"{RUN}-renamed"
        if (
            await run.call(
                "repos_rename_branch",
                **repo_args(),
                branch=spare,
                new_name=renamed,
                expect=lambda r: r.get("name") == renamed,
            )
            is not None
        ):
            run.state["spare_branch"] = renamed

    await run.call(
        "repos_merge_branches",
        **repo_args(),
        base=branch,
        head="main",
        commit_message=f"{RUN}: merge main into the work branch",
        allow_status=(409,),
        note="already up to date, or a conflict",
    )


# -----------------------------------------------------
# Phase 3 — issues, and everything hung off one
# -----------------------------------------------------


async def phase_issues(run: Run) -> None:
    label = f"{RUN}-label"
    created_label = await run.call(
        "issues_create_label",
        **repo_args(),
        name=label,
        color="ededed",
        description="Created by the live check.",
        expect=lambda r: r.get("name") == label,
    )
    await run.call(
        "issues_list_labels_for_repo",
        **repo_args(),
        per_page=100,
        expect=lambda r: any(item["name"] == label for item in r) if created_label else True,
    )
    if created_label:
        await run.call(
            "issues_update_label",
            **repo_args(),
            name=label,
            description="Edited by the live check.",
            expect=lambda r: r.get("description") == "Edited by the live check.",
        )

    milestone = await run.call(
        "issues_create_milestone",
        **repo_args(),
        title=f"{RUN} milestone",
        description="Created by the live check.",
        expect=lambda r: bool(r.get("number")),
    )
    await run.call("issues_list_milestones", **repo_args(), expect=lambda r: isinstance(r, list))
    if milestone:
        await run.call(
            "issues_update_milestone",
            **repo_args(),
            milestone_number=milestone["number"],
            state="closed",
            expect=lambda r: r.get("state") == "closed",
        )

    issue = await run.call(
        "issues_create",
        **repo_args(),
        body={"title": f"{RUN}: live check", "body": "Opened by the live check."},
        expect=lambda r: bool(r.get("number")),
    )
    if not issue:
        return
    number = issue["number"]
    run.state["issue"] = number

    await run.call(
        "issues_get", **repo_args(), issue_number=number, expect=lambda r: r["number"] == number
    )
    await run.call(
        "issues_list_for_repo", **repo_args(), per_page=5, expect=lambda r: isinstance(r, list)
    )
    await run.call(
        "issues_list_for_authenticated_user",
        filter="created",
        per_page=5,
        expect=lambda r: isinstance(r, list),
    )
    await run.call(
        "issues_update",
        **repo_args(),
        issue_number=number,
        body={"body": "Edited by the live check."},
        expect=lambda r: r.get("body") == "Edited by the live check.",
    )

    if created_label:
        await run.call(
            "issues_add_labels",
            **repo_args(),
            issue_number=number,
            labels=[label],
            expect=lambda r: any(item["name"] == label for item in r),
        )
        await run.call(
            "issues_set_labels",
            **repo_args(),
            issue_number=number,
            labels=[label],
            expect=lambda r: [item["name"] for item in r] == [label],
        )
        await run.call(
            "issues_remove_label",
            **repo_args(),
            issue_number=number,
            name=label,
            expect=lambda r: isinstance(r, list),
        )

    login = run.state.get("login")
    if login:
        await run.call(
            "issues_add_assignees",
            **repo_args(),
            issue_number=number,
            assignees=[login],
            expect=lambda r: login in (r.get("assignees") or []),
        )
        await run.call(
            "issues_remove_assignees",
            **repo_args(),
            issue_number=number,
            assignees=[login],
            expect=lambda r: login not in (r.get("assignees") or []),
        )

    comment = await run.call(
        "issues_create_comment",
        **repo_args(),
        issue_number=number,
        body={"body": "A comment from the live check."},
        expect=lambda r: bool(r.get("id")),
    )
    await run.call(
        "issues_list_comments",
        **repo_args(),
        issue_number=number,
        expect=lambda r: isinstance(r, list),
    )
    if comment:
        await run.call(
            "issues_get_comment",
            **repo_args(),
            comment_id=comment["id"],
            expect=lambda r: r["id"] == comment["id"],
        )
        await run.call(
            "issues_update_comment",
            **repo_args(),
            comment_id=comment["id"],
            body="Edited by the live check.",
            expect=lambda r: r.get("body") == "Edited by the live check.",
        )
        await run.call("issues_delete_comment", **repo_args(), comment_id=comment["id"])

    await run.call("issues_lock", **repo_args(), issue_number=number, lock_reason="resolved")
    await run.call("issues_unlock", **repo_args(), issue_number=number)
    await run.call(
        "issues_list_events",
        **repo_args(),
        issue_number=number,
        expect=lambda r: isinstance(r, list),
    )
    await run.call(
        "issues_list_timeline",
        **repo_args(),
        issue_number=number,
        expect=lambda r: isinstance(r, list),
    )

    # Sub-issues need a second issue, and take its *id*, not its number — which
    # is the thing most likely to be got wrong, so it is exercised.
    child = await run.call(
        "issues_create",
        **repo_args(),
        body={"title": f"{RUN}: child", "body": "A sub-issue."},
        expect=lambda r: bool(r.get("number")),
    )
    if child:
        run.state["child_issue"] = child["number"]
        raw = await _raw_issue(child["number"])
        if raw:
            await run.call(
                "issues_add_sub_issue",
                **repo_args(),
                issue_number=number,
                sub_issue_id=raw["id"],
                expect=lambda r: bool(r.get("number")),
            )
        await run.call(
            "issues_list_sub_issues",
            **repo_args(),
            issue_number=number,
            expect=lambda r: isinstance(r, list),
        )


async def _raw_issue(number: int) -> Optional[Dict[str, Any]]:
    """The issue's database id, which the pack's projection deliberately drops.

    `issues_add_sub_issue` is the one endpoint that wants it, and the trimmed
    issue does not carry it — so it is fetched here rather than widening every
    issue in the pack by a field nothing else uses.
    """
    import httpx

    token = os.environ["GITHUB_TOKEN"]
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            f"https://api.github.com/repos/{REPO}/issues/{number}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "charter-live-check",
            },
        )
    return resp.json() if resp.status_code == 200 else None


# -----------------------------------------------------
# Phase 4 — a pull request, and reviewing it line by line
# -----------------------------------------------------


async def phase_pulls(run: Run) -> None:
    branch = run.state.get("branch")
    if not branch:
        return

    pull = await run.call(
        "pulls_create",
        **repo_args(),
        body={
            "title": f"{RUN}: live check",
            "head": branch,
            "base": "main",
            "body": "Opened by the live check.",
        },
        expect=lambda r: bool(r.get("number")),
    )
    if not pull:
        return
    number = pull["number"]
    run.state["pull"] = number

    await run.call(
        "pulls_get", **repo_args(), pull_number=number, expect=lambda r: r["number"] == number
    )
    await run.call("pulls_list", **repo_args(), per_page=5, expect=lambda r: isinstance(r, list))
    await run.call(
        "pulls_get_diff",
        **repo_args(),
        pull_number=number,
        expect=lambda r: r.get("files_changed", 0) >= 1 and "diff --git" in r.get("diff", ""),
    )
    files = await run.call(
        "pulls_list_files", **repo_args(), pull_number=number, expect=lambda r: len(r) >= 1
    )
    commits = await run.call(
        "pulls_list_commits", **repo_args(), pull_number=number, expect=lambda r: len(r) >= 1
    )
    await run.call(
        "pulls_update",
        **repo_args(),
        pull_number=number,
        body="Edited by the live check.",
        expect=lambda r: r.get("body") == "Edited by the live check.",
    )
    await run.call(
        "pulls_check_merged",
        **repo_args(),
        pull_number=number,
        allow_status=(404,),
        note="not merged yet, which this endpoint reports as a 404",
    )
    await run.call(
        "pulls_update_branch",
        **repo_args(),
        pull_number=number,
        allow_status=(422,),
        note="already up to date with base",
    )

    # A comment on a line of the diff — the primitive this pack was missing.
    head_sha = commits[-1]["sha"] if commits else run.state.get("commit_sha")
    path = files[0]["filename"] if files else f"{RUN}/one.txt"
    line_comment = None
    if head_sha:
        line_comment = await run.call(
            "pulls_create_review_comment",
            **repo_args(),
            pull_number=number,
            body="A remark on this line, from the live check.",
            commit_id=head_sha,
            path=path,
            line=1,
            side="RIGHT",
            expect=lambda r: r.get("path") == path and r.get("line") == 1,
        )
    await run.call(
        "pulls_list_review_comments",
        **repo_args(),
        pull_number=number,
        expect=lambda r: isinstance(r, list),
    )
    await run.call(
        "pulls_list_review_comments_for_repo",
        **repo_args(),
        per_page=5,
        expect=lambda r: isinstance(r, list),
    )
    if line_comment:
        await run.call(
            "pulls_reply_to_review_comment",
            **repo_args(),
            pull_number=number,
            comment_id=line_comment["id"],
            body="And a reply to it.",
            expect=lambda r: bool(r.get("id")),
        )
        await run.call(
            "pulls_update_review_comment",
            **repo_args(),
            comment_id=line_comment["id"],
            body="Edited by the live check.",
            expect=lambda r: r.get("body") == "Edited by the live check.",
        )
        await run.call("pulls_delete_review_comment", **repo_args(), comment_id=line_comment["id"])

    # GitHub refuses an APPROVE on your own pull request, so the review is a
    # COMMENT — which is the one an agent leaves anyway.
    review = await run.call(
        "pulls_create_review",
        **repo_args(),
        pull_number=number,
        event="COMMENT",
        body="A review from the live check.",
        expect=lambda r: bool(r.get("id")),
    )
    await run.call(
        "pulls_list_reviews",
        **repo_args(),
        pull_number=number,
        expect=lambda r: isinstance(r, list),
    )
    if review:
        rid = review["id"]
        await run.call(
            "pulls_get_review",
            **repo_args(),
            pull_number=number,
            review_id=rid,
            expect=lambda r: r["id"] == rid,
        )
        await run.call(
            "pulls_list_comments_for_review",
            **repo_args(),
            pull_number=number,
            review_id=rid,
            expect=lambda r: isinstance(r, list),
        )
        await run.call(
            "pulls_update_review",
            **repo_args(),
            pull_number=number,
            review_id=rid,
            body="Edited by the live check.",
            expect=lambda r: r.get("body") == "Edited by the live check.",
        )
        await run.call(
            "pulls_dismiss_review",
            **repo_args(),
            pull_number=number,
            review_id=rid,
            message="Dismissed by the live check.",
            allow_status=(422,),
            note="only a review that blocks the pull request can be dismissed",
        )

    # A pending review, so the two tools that only apply to one are exercised.
    pending = await _raw_pending_review(number)
    if pending:
        await run.call(
            "pulls_submit_review",
            **repo_args(),
            pull_number=number,
            review_id=pending,
            event="COMMENT",
            body="Submitted by the live check.",
            expect=lambda r: r.get("state") == "COMMENTED",
        )
    second_pending = await _raw_pending_review(number)
    if second_pending:
        await run.call(
            "pulls_delete_pending_review",
            **repo_args(),
            pull_number=number,
            review_id=second_pending,
            expect=lambda r: bool(r.get("id")),
        )

    # You cannot request a review from yourself, so this is the documented 422.
    login = run.state.get("login")
    if login:
        await run.call(
            "pulls_request_reviewers",
            **repo_args(),
            pull_number=number,
            reviewers=[login],
            allow_status=(422,),
            note="GitHub refuses a review request to the pull request's author",
        )
    await run.call(
        "pulls_list_requested_reviewers",
        **repo_args(),
        pull_number=number,
        expect=lambda r: isinstance(r, dict),
    )
    await run.call(
        "pulls_remove_requested_reviewers",
        **repo_args(),
        pull_number=number,
        reviewers=[login] if login else [],
        allow_status=(422,),
        note="nobody was successfully requested, so there is nobody to remove",
    )

    merged = await run.call(
        "pulls_merge",
        **repo_args(),
        pull_number=number,
        merge_method="squash",
        allow_status=(405, 409),
        note="the branch was not mergeable at this point",
    )
    if merged is not None:
        run.state["merged_pull"] = True
        await run.call(
            "pulls_check_merged",
            **repo_args(),
            pull_number=number,
            expect=lambda r: r == {"merged": True},
        )


async def _raw_pending_review(pull_number: int) -> Optional[int]:
    """Create a PENDING review directly, to give the submit/delete tools a subject.

    ``pulls_create_review`` in this pack *requires* an ``event``, deliberately —
    a review left pending by a tool with no way to finish it is a review nobody
    can see. So the fixture is made outside the pack, and the pack's tools are
    what act on it.
    """
    import httpx

    token = os.environ["GITHUB_TOKEN"]
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            f"https://api.github.com/repos/{REPO}/pulls/{pull_number}/reviews",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "charter-live-check",
            },
            json={"body": "Pending, for the live check."},
        )
    return resp.json().get("id") if resp.status_code in (200, 201) else None


# -----------------------------------------------------
# Phase 5 — CI, which needs a workflow that has actually run
# -----------------------------------------------------

# Everything the CI phase reaches, named once so that a phase which cannot run
# reports every tool it covers rather than one.
_CI_TOOLS = {
    "actions_get_workflow",
    "actions_create_workflow_dispatch",
    "actions_list_runs_for_workflow",
    "actions_get_workflow_run",
    "actions_list_jobs_for_run",
    "actions_get_job",
    "actions_download_job_logs",
    "actions_download_run_logs",
    "actions_list_run_artifacts",
    "actions_get_artifact",
    "actions_download_artifact",
    "actions_get_run_usage",
    "actions_rerun_failed_jobs",
    "actions_rerun_workflow",
    "actions_cancel_workflow_run",
    "actions_list_pending_deployments",
    "actions_list_repo_secrets",
    "actions_list_workflows",
    "actions_list_workflow_runs",
    "checks_get_run",
    "checks_list_annotations",
}

WORKFLOW = f"""\
name: {RUN}
on: workflow_dispatch
jobs:
  pass:
    runs-on: ubuntu-latest
    steps:
      - run: echo "the live check ran this"
      # A block scalar, because a plain one ends at the first ": " — which is
      # inside the JSON, and which made GitHub fail to parse the whole file and
      # register no triggers at all.
      - run: |
          mkdir -p out
          echo '{{"ok":true}}' > out/report.json
      - uses: actions/upload-artifact@v4
        with:
          name: {RUN}-report
          path: out/
  fail:
    runs-on: ubuntu-latest
    steps:
      - run: echo "about to fail on purpose"
      - run: |
          echo "::error::the live check made this job fail"
          exit 1
"""


async def phase_actions(run: Run, *, wait: int) -> None:
    """The CI block, against a workflow this run puts there and triggers.

    A repository with no workflow has no run, no job and no log, and reading
    those tools against an empty list proves only that the URL resolves. So the
    workflow is seeded on the default branch — GitHub only dispatches what is on
    the default branch — with one job that passes and uploads an artifact and one
    that fails loudly, which is the shape the log and annotation tools are for.
    """
    path = f".github/workflows/{RUN}.yml"
    seeded = await run.call(
        "repos_create_or_update_file",
        **repo_args(),
        path=path,
        message=f"{RUN}: seed a workflow",
        content=WORKFLOW,
        branch="main",
        expect=lambda r: bool(r.get("content", {}).get("sha")),
        # Writing under `.github/workflows` needs the `workflow` scope, which a
        # plain `repo` token does not have — and GitHub answers 404 rather than
        # 403, so the failure looks like a missing repository. Named here so a
        # run with the wrong token reports the reason instead of the symptom.
        allow_status=(404, 403),
        note="the workflow must be on the default branch to be dispatchable",
    )
    if seeded:
        run.state["workflow_path"] = path
        run.state["workflow_sha"] = seeded["content"]["sha"]
    else:
        why = (
            "seeding .github/workflows needs a token with the `workflow` scope; "
            "re-run with one to exercise the CI tools"
        )
        for name in _CI_TOOLS:
            run.skip(name, why)
        return

    if not seeded:
        run.skip("actions_get_workflow", "the workflow could not be seeded")
        return

    # A workflow appears in this listing a beat after the commit that added it,
    # and `actions_get_workflow` finds it by filename before it does. Waited out
    # rather than reported: an empty list here is GitHub still indexing, not the
    # tool returning the wrong thing.
    for attempt in range(12):
        listed = await github.actions_list_workflows.ainvoke(**repo_args())
        if any(w.get("path") == path for w in listed.get("workflows", [])):
            run.outcomes.append(
                Outcome(
                    "actions_list_workflows",
                    "pass",
                    f"the seeded workflow is registered (after {attempt + 1} attempt(s))",
                )
            )
            break
        await asyncio.sleep(5)
    else:
        run.outcomes.append(
            Outcome(
                "actions_list_workflows",
                "fail",
                "the seeded workflow never appeared in the listing",
            )
        )
    registered = await run.call(
        "actions_get_workflow",
        **repo_args(),
        workflow_id=f"{RUN}.yml",
        expect=lambda r: r.get("path") == path,
    )
    # GitHub reports a workflow it could not parse by showing the *path* where
    # the name should be, and registers none of its triggers — which then
    # surfaces as a 422 on dispatch that blames the trigger rather than the
    # YAML. Reading the name says which it is, immediately.
    if registered and registered.get("name", "").endswith(".yml"):
        for name in _CI_TOOLS - {"actions_get_workflow", "actions_list_workflows"}:
            run.skip(name, f"GitHub could not parse {path}, so it has no triggers")
        return
    # A workflow pushed a second ago exists but is not yet dispatchable: GitHub
    # answers 422 "Workflow does not have 'workflow_dispatch' trigger" until it
    # has indexed the file. That is a property of the seeding, not of the tool,
    # so it is waited out rather than reported as a failure.
    dispatched = False
    for attempt in range(12):
        try:
            await github.actions_create_workflow_dispatch.ainvoke(
                **repo_args(),
                workflow_id=f"{RUN}.yml",
                ref="main",
                return_run_details=True,
            )
        except APIError as exc:
            if getattr(exc, "status_code", None) != 422 or attempt == 11:
                run.outcomes.append(
                    Outcome("actions_create_workflow_dispatch", "fail", str(exc)[:200])
                )
                break
            await asyncio.sleep(5)
            continue
        dispatched = True
        run.outcomes.append(
            Outcome(
                "actions_create_workflow_dispatch",
                "pass",
                f"triggered the seeded workflow after {attempt + 1} attempt(s)",
            )
        )
        break

    if not dispatched:
        for name in _CI_TOOLS - {
            "actions_get_workflow",
            "actions_create_workflow_dispatch",
            "actions_list_workflows",
        }:
            run.skip(name, "the workflow was never dispatchable, so there is no run to read")
        return

    if wait <= 0:
        for name in _CI_TOOLS - {"actions_get_workflow", "actions_create_workflow_dispatch"}:
            run.skip(name, "--wait 0: the run was dispatched but not waited for")
        return

    run_id = await _await_run(run, wait)
    if run_id is None:
        return

    await run.call(
        "actions_get_workflow_run",
        **repo_args(),
        run_id=run_id,
        expect=lambda r: r.get("id") == run_id,
    )
    await run.call(
        "actions_list_workflow_runs",
        **repo_args(),
        per_page=5,
        expect=lambda r: "workflow_runs" in r,
    )
    await run.call(
        "actions_list_pending_deployments",
        **repo_args(),
        run_id=run_id,
        expect=lambda r: isinstance(r, list),
    )
    await run.call(
        "actions_get_run_usage",
        **repo_args(),
        run_id=run_id,
        allow_status=(403, 404, 410),
        note="GitHub has this endpoint closing down",
    )

    jobs = await run.call(
        "actions_list_jobs_for_run",
        **repo_args(),
        run_id=run_id,
        expect=lambda r: len(r.get("jobs", [])) >= 1,
    )
    if not jobs:
        return
    failed = next((j for j in jobs["jobs"] if j.get("conclusion") == "failure"), None)
    subject = failed or jobs["jobs"][0]

    await run.call(
        "actions_get_job",
        **repo_args(),
        job_id=subject["id"],
        expect=lambda r: r.get("id") == subject["id"],
    )

    # The one that matters: a real failing job's real log, reduced.
    await run.call(
        "actions_download_job_logs",
        **repo_args(),
        job_id=subject["id"],
        expect=lambda r: r.get("total_lines", 0) > 0 and isinstance(r.get("tail"), str),
        note=("read the failing job's log" if failed else "read a job log"),
    )
    await run.call(
        "actions_download_run_logs",
        **repo_args(),
        run_id=run_id,
        expect=lambda r: r.get("job_count", 0) >= 1,
    )

    # The annotation the failing job emitted with ::error::, already located by
    # GitHub — the cheap answer to "why is CI red" that this whole block exists
    # to make reachable. Check runs appear a little after the jobs they describe,
    # so this waits for them rather than reading an empty list and moving on.
    head = (
        await run.call(
            "actions_get_workflow_run",
            **repo_args(),
            run_id=run_id,
            expect=lambda r: bool(r.get("head_sha")),
        )
        or {}
    ).get("head_sha")

    check = []
    if head:
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            listed = await run.call(
                "checks_list_for_ref",
                **repo_args(),
                ref=head,
                expect=lambda r: "check_runs" in r,
            )
            check = (listed or {}).get("check_runs", [])
            if check:
                break
            await asyncio.sleep(10)

    if check:
        # The failing check run, where the annotation is.
        subject_check = next((c for c in check if c.get("conclusion") == "failure"), check[0])
        await run.call(
            "checks_get_run",
            **repo_args(),
            check_run_id=subject_check["id"],
            expect=lambda r: bool(r.get("id")),
        )
        await run.call(
            "checks_list_annotations",
            **repo_args(),
            check_run_id=subject_check["id"],
            expect=lambda r: isinstance(r, list),
            note="the ::error:: the failing job emitted, with its file and line",
        )
    else:
        run.skip("checks_get_run", "no check run registered against the run's head within 90s")
        run.skip("checks_list_annotations", "no check run to read annotations from")

    if failed:
        await run.call(
            "actions_rerun_failed_jobs",
            **repo_args(),
            run_id=run_id,
            note="asked GitHub to retry the failing job",
        )

    # A full rerun, and a cancel — the two lifecycle tools the pack already had,
    # now against a run this script can account for. The rerun is not waited on.
    await run.call(
        "actions_rerun_workflow",
        **repo_args(),
        run_id=run_id,
        allow_status=(403,),
        note="re-ran every job, including the ones that passed",
    )
    await _dispatch_and_cancel(run)

    artifacts = await run.call(
        "actions_list_run_artifacts",
        **repo_args(),
        run_id=run_id,
        expect=lambda r: "artifacts" in r,
    )
    items = (artifacts or {}).get("artifacts", [])
    if items:
        await run.call(
            "actions_get_artifact",
            **repo_args(),
            artifact_id=items[0]["id"],
            expect=lambda r: bool(r.get("name")),
        )
        await run.call(
            "actions_download_artifact",
            **repo_args(),
            artifact_id=items[0]["id"],
            expect=lambda r: r.get("entry_count", 0) >= 1,
        )
    else:
        run.skip("actions_get_artifact", "the run uploaded no artifact")
        run.skip("actions_download_artifact", "the run uploaded no artifact")

    await run.call("actions_list_repo_secrets", **repo_args(), expect=lambda r: "secrets" in r)


async def _dispatch_and_cancel(run: Run) -> None:
    """Start one more run purely so there is something to cancel.

    Cancelling needs a run that has not finished, and the completed one above is
    the wrong subject. This dispatches a second, waits for it to appear, and
    stops it — which also leaves the sandbox with one fewer minute spent.
    """
    try:
        before = await github.actions_list_runs_for_workflow.ainvoke(
            **repo_args(), workflow_id=f"{RUN}.yml", per_page=1
        )
        known = {r["id"] for r in before.get("workflow_runs") or []}
        await github.actions_create_workflow_dispatch.ainvoke(
            **repo_args(), workflow_id=f"{RUN}.yml", ref="main"
        )
    except Exception as exc:  # noqa: BLE001
        run.skip("actions_cancel_workflow_run", f"could not start a run to cancel: {exc}")
        return

    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            page = await github.actions_list_runs_for_workflow.ainvoke(
                **repo_args(), workflow_id=f"{RUN}.yml", per_page=3
            )
        except Exception as exc:  # noqa: BLE001
            run.skip("actions_cancel_workflow_run", f"could not list runs: {exc}")
            return
        fresh = [r for r in page.get("workflow_runs") or [] if r["id"] not in known]
        if fresh:
            await run.call(
                "actions_cancel_workflow_run",
                **repo_args(),
                run_id=fresh[0]["id"],
                allow_status=(409,),
                note=f"cancelled run {fresh[0]['id']}",
            )
            return
        await asyncio.sleep(5)

    run.skip("actions_cancel_workflow_run", "the second dispatch produced no run within 60s")


async def _await_run(run: Run, wait: int) -> Optional[int]:
    """Poll until the dispatched run has finished, or give up and say so."""
    deadline = time.monotonic() + wait
    run_id = None
    while time.monotonic() < deadline:
        try:
            page = await github.actions_list_runs_for_workflow.ainvoke(
                **repo_args(), workflow_id=f"{RUN}.yml", per_page=1
            )
        except Exception as exc:  # noqa: BLE001
            run.outcomes.append(Outcome("actions_list_runs_for_workflow", "fail", str(exc)[:200]))
            return None
        runs = page.get("workflow_runs") or []
        if runs:
            run_id = runs[0]["id"]
            if runs[0].get("status") == "completed":
                run.outcomes.append(
                    Outcome(
                        "actions_list_runs_for_workflow",
                        "pass",
                        f"run {run_id} finished as {runs[0].get('conclusion')}",
                    )
                )
                return run_id
        await asyncio.sleep(10)

    if run_id is None:
        run.outcomes.append(
            Outcome("actions_list_runs_for_workflow", "fail", "the dispatch produced no run")
        )
        return None
    run.outcomes.append(
        Outcome(
            "actions_list_runs_for_workflow",
            "pass",
            f"run {run_id} was still going after {wait}s; reading it anyway",
        )
    )
    return run_id


# -----------------------------------------------------
# Phase 6 — releases
# -----------------------------------------------------


async def phase_releases(run: Run) -> None:
    await run.call(
        "releases_generate_notes",
        **repo_args(),
        tag_name=f"{RUN}-notes",
        expect=lambda r: set(r) <= {"name", "body"} and bool(r.get("body")),
        note="returns text and saves nothing, which is the whole point of it",
    )

    release = await run.call(
        "releases_create",
        **repo_args(),
        tag_name=f"{RUN}-rel",
        name=f"{RUN} release",
        body="Created by the live check.",
        draft=True,
        expect=lambda r: bool(r.get("id")),
    )
    await run.call("releases_list", **repo_args(), per_page=5, expect=lambda r: isinstance(r, list))
    await run.call(
        "releases_get_latest",
        **repo_args(),
        allow_status=(404,),
        note="the sandbox has no published release",
    )
    if not release:
        return
    rid = release["id"]
    run.state["release"] = rid

    await run.call("releases_get", **repo_args(), release_id=rid, expect=lambda r: r["id"] == rid)
    await run.call(
        "releases_update",
        **repo_args(),
        release_id=rid,
        body="Edited by the live check.",
        expect=lambda r: r.get("body") == "Edited by the live check.",
    )
    await run.call(
        "releases_upload_asset",
        **repo_args(),
        release_id=rid,
        name=f"{RUN}-checksums.txt",
        content="d41d8cd98f00b204e9800998ecf8427e  empty\n",
        expect=lambda r: r.get("state") == "uploaded",
        note="posted raw bytes to uploads.github.com",
    )
    await run.call(
        "releases_list_assets", **repo_args(), release_id=rid, expect=lambda r: len(r) >= 1
    )

    # A draft has no tag: GitHub replaces `tag_name` with an `untagged-…`
    # placeholder until the release is published, so publishing has to say the
    # tag again or it is created under the placeholder. Found by this script —
    # `releases_get_by_tag` was a 404 and the reason was three calls earlier.
    published = await run.call(
        "releases_update",
        **repo_args(),
        release_id=rid,
        draft=False,
        tag_name=f"{RUN}-rel",
        expect=lambda r: r.get("draft") is not True and r.get("tag_name") == f"{RUN}-rel",
    )
    if published:
        await run.call(
            "releases_get_by_tag",
            **repo_args(),
            tag=f"{RUN}-rel",
            expect=lambda r: r.get("tag_name") == f"{RUN}-rel",
        )


# -----------------------------------------------------
# Phase 7 — search, notifications, security
# -----------------------------------------------------


async def phase_discovery(run: Run) -> None:
    await run.call(
        "search_issues", q=f"repo:{REPO} {RUN}", per_page=5, expect=lambda r: "items" in r
    )
    await run.call(
        "search_repositories",
        q="charter language:python",
        per_page=5,
        expect=lambda r: "items" in r,
    )
    await run.call(
        "search_code",
        q=f"repo:{REPO} charter",
        per_page=5,
        allow_status=(403, 422),
        note="code search is indexed separately and rate limited",
    )
    await run.call(
        "search_commits", q=f"repo:{REPO} {RUN}", per_page=5, expect=lambda r: "items" in r
    )
    await run.call("search_users", q="type:org charter", per_page=5, expect=lambda r: "items" in r)

    threads = await run.call(
        "notifications_list", per_page=5, all=True, expect=lambda r: isinstance(r, list)
    )
    if threads:
        await run.call(
            "notifications_get_thread",
            thread_id=int(threads[0]["id"]),
            expect=lambda r: bool(r.get("reason")),
        )
    else:
        run.skip("notifications_get_thread", "the account has no notifications to read")

    await run.call(
        "dependabot_list_alerts",
        **repo_args(),
        per_page=5,
        allow_status=(403, 404),
        note="Dependabot is not enabled on the sandbox",
    )
    await run.call(
        "dependabot_get_alert",
        **repo_args(),
        alert_number=1,
        allow_status=(403, 404),
        note="no alert 1 on the sandbox",
    )
    await run.call(
        "code_scanning_list_alerts",
        **repo_args(),
        per_page=5,
        allow_status=(403, 404),
        note="code scanning is not configured on the sandbox",
    )
    await run.call(
        "code_scanning_get_alert",
        **repo_args(),
        alert_number=1,
        allow_status=(403, 404),
        note="no alert 1 on the sandbox",
    )
    await run.call(
        "secret_scanning_list_alerts",
        **repo_args(),
        per_page=5,
        hide_secret=True,
        allow_status=(403, 404),
        note="secret scanning is not enabled on the sandbox",
    )


# -----------------------------------------------------
# Teardown — everything this run put there, taken back out
# -----------------------------------------------------


async def teardown(run: Run) -> List[str]:
    """Remove the run's fixtures, reporting what could not be removed.

    Runs after a failure too. A sandbox that fills up with a hundred abandoned
    branches is a sandbox nobody trusts the next result from.
    """
    left: List[str] = []

    async def attempt(tool: str, what: str, **kwargs: Any) -> None:
        """Remove one fixture, and count the removal as the coverage it is.

        The delete tools have nowhere else to run: a check that created a label
        and never removed it would be testing half of `issues_delete_label` and
        filling the sandbox with the other half. So teardown goes through the
        same recorder, with 404 and 422 read as "there was nothing left to
        remove" — which is the state this is trying to reach.
        """
        before = len(run.outcomes)
        await run.call(tool, allow_status=(404, 422), note=f"removed {what}", **kwargs)
        if run.outcomes[before].status == "fail":
            left.append(f"{what}: {run.outcomes[before].detail}")

    if (rid := run.state.get("release")) is not None:
        await attempt("releases_delete", f"release {rid}", **repo_args(), release_id=rid)
        await attempt("git_refs_delete", f"tag {RUN}-rel", **repo_args(), ref=f"tags/{RUN}-rel")

    for number_key in ("child_issue", "issue"):
        if (number := run.state.get(number_key)) is not None:
            await attempt(
                "issues_update",
                f"issue #{number}",
                **repo_args(),
                issue_number=number,
                body={"state": "closed", "state_reason": "not_planned"},
            )

    if (number := run.state.get("pull")) is not None and not run.state.get("merged_pull"):
        await attempt(
            "pulls_update", f"pull #{number}", **repo_args(), pull_number=number, state="closed"
        )

    if (path := run.state.get("workflow_path")) is not None:
        # Read the sha again: the dispatch does not change the file, but a rerun
        # of this script against a repository someone else touched might have.
        try:
            current = await github.repos_get_content.ainvoke(**repo_args(), path=path)
            sha = current.get("sha") or run.state.get("workflow_sha")
        except Exception:  # noqa: BLE001
            sha = run.state.get("workflow_sha")
        if sha:
            await attempt(
                "repos_delete_file",
                f"workflow {path}",
                **repo_args(),
                path=path,
                message=f"{RUN}: remove the seeded workflow",
                sha=sha,
                branch="main",
            )

    for key in ("branch", "spare_branch"):
        if (branch := run.state.get(key)) is not None:
            await attempt(
                "git_refs_delete", f"branch {branch}", **repo_args(), ref=f"heads/{branch}"
            )

    if run.state.get("tag"):
        await attempt(
            "git_refs_delete",
            f"tag {run.state['tag']}",
            **repo_args(),
            ref=f"tags/{run.state['tag']}",
        )

    await attempt("issues_delete_label", f"label {RUN}-label", **repo_args(), name=f"{RUN}-label")

    return left


# -----------------------------------------------------
# Reporting
# -----------------------------------------------------


def report(run: Run, leftovers: List[str]) -> int:
    seen = {o.tool for o in run.outcomes}
    everything = {t.name for t in github.TOOLS}
    unvisited = sorted(everything - seen - set(SKIPPED))

    width = max(len(o.tool) for o in run.outcomes) if run.outcomes else 20
    order = {"fail": 0, "expected": 1, "pass": 2, "skip": 3}
    mark = {"pass": "ok  ", "fail": "FAIL", "expected": "ok* ", "skip": "skip"}

    print(f"\n{'=' * 78}\nlive check against {REPO}   (run id {RUN})\n{'=' * 78}")
    for outcome in sorted(run.outcomes, key=lambda o: (order[o.status], o.tool)):
        print(f"  {mark[outcome.status]}  {outcome.tool:<{width}}  {outcome.detail}")

    counts = {status: sum(1 for o in run.outcomes if o.status == status) for status in order}
    print(
        f"\n{counts['pass']} passed, {counts['expected']} answered as documented "
        f"(ok*), {counts['fail']} failed, {counts['skip'] + len(SKIPPED)} skipped"
    )

    if SKIPPED:
        print("\nnot run, by choice:")
        for tool, why in sorted(SKIPPED.items()):
            print(f"  skip  {tool:<{width}}  {why}")

    if unvisited:
        print(f"\nnever reached ({len(unvisited)}):")
        for tool in unvisited:
            print(f"  ????  {tool}")

    if leftovers:
        print("\nnot cleaned up — remove these by hand:")
        for item in leftovers:
            print(f"  !!    {item}")

    return 1 if (counts["fail"] or unvisited or leftovers) else 0


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--wait",
        type=int,
        default=300,
        help="seconds to wait for the dispatched workflow run to finish (0 to skip the CI phase)",
    )
    parser.add_argument(
        "--no-teardown",
        action="store_true",
        help="leave the run's fixtures in place, to look at them",
    )
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("set GITHUB_TOKEN (try: export GITHUB_TOKEN=$(gh auth token))", file=sys.stderr)
        return 2
    github.configure(StaticTokenProvider(token))

    run = Run()
    for tool, why in SKIPPED.items():
        run.skip(tool, why)

    phases = [
        ("reads", phase_reads(run)),
        ("git", phase_git(run)),
        ("issues", phase_issues(run)),
        ("pulls", phase_pulls(run)),
        ("actions", phase_actions(run, wait=args.wait)),
        ("releases", phase_releases(run)),
        ("discovery", phase_discovery(run)),
    ]
    # Each phase is isolated. A raise in one used to skip every phase after it,
    # which turned one broken fixture into thirty tools reported as unreached —
    # a result that says nothing about the thirty.
    for name, coro in phases:
        try:
            await coro
        except Exception:  # noqa: BLE001 - the other phases are still worth running
            traceback.print_exc()
            run.outcomes.append(
                Outcome(f"<phase {name}>", "fail", "raised; see the traceback above")
            )

    leftovers = [] if args.no_teardown else await teardown(run)
    return report(run, leftovers)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
