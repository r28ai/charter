"""GitHub, against the real API, inside one sandbox repository.

Every write here targets ``<GITHUB_OWNER>/harness-*`` and nothing else. The
harness guard enforces that on the arms; these tests are not under the guard, so
:func:`sandbox_repo` asserts the prefix itself before a single call is made.

The headline is ``repos_create_or_update_file``. Its ``content`` field carries a
``Format`` transform to base64, and until the last release a lone ``Format`` body
field replaced the *whole* request body with its own transformed value — so the
first file this pack ever wrote sent a bare base64 string and no commit message.
A respx mock cannot see that; it answers whatever it was told to. GitHub cannot
help but see it. That is the shape of everything in this directory.
"""

from __future__ import annotations

import pytest
from charter.packs import github
from charter.types.errors import APIError

from charter_harness.world import eventually

pytestmark = pytest.mark.live


async def _head_sha(owner: str, repo: str, branch: str) -> str:
    commits = await github.repos_list_commits.ainvoke(
        {"owner": owner, "repo": repo, "sha": branch, "per_page": 1}
    )
    return commits[0]["sha"]


# -----------------------------------------------------
# Contents, branches, pull requests: the round trip
# -----------------------------------------------------


async def test_a_file_is_written_read_reviewed_and_merged(
    needs, world, trash, run_tag, github_owner, sandbox_repo
):
    """Branch, write a file, open a pull request, review it, merge it.

    Eight tools in one sequence because that is how they are used, and because
    every step depends on the last one having really happened — a mock chain
    proves only that eight requests were shaped as the mock expected.
    """
    needs("github")
    owner, repo = github_owner, sandbox_repo
    branch = f"live/{run_tag}"
    path = f"live/{run_tag}.md"
    body = f"# live check {run_tag}\n\nWritten by the live suite, deleted by it.\n"

    base = await github.repos_get.ainvoke({"owner": owner, "repo": repo})
    assert base["default_branch"] == "main"

    await github.git_refs_create.ainvoke(
        {
            "owner": owner,
            "repo": repo,
            "ref": f"refs/heads/{branch}",
            "sha": await _head_sha(owner, repo, base["default_branch"]),
        }
    )
    trash.later(lambda: world.github.branch_delete(branch))

    listed = await github.branches_list.ainvoke({"owner": owner, "repo": repo, "per_page": 100})
    assert branch in [b["name"] for b in listed]

    # `content` is the transformed field; when its transform ate the body,
    # `message` never arrived and GitHub answered 422.
    written = await github.repos_create_or_update_file.ainvoke(
        {
            "owner": owner,
            "repo": repo,
            "path": path,
            "message": f"live check {run_tag}",
            "content": body,
            "branch": branch,
        }
    )
    assert written["commit"]["message"] == f"live check {run_tag}"
    commits = await github.repos_list_commits.ainvoke(
        {"owner": owner, "repo": repo, "sha": branch, "per_page": 1}
    )
    assert commits[0]["sha"] == written["commit"]["sha"]

    # And the content survived the round trip as text, not as base64 of base64.
    read_back = await github.repos_get_content.ainvoke(
        {"owner": owner, "repo": repo, "path": path, "ref": branch}
    )
    assert read_back["content"] == body

    pull = await github.pulls_create.ainvoke(
        {
            "owner": owner,
            "repo": repo,
            "body": {
                "title": f"Live check {run_tag}",
                "head": branch,
                "base": base["default_branch"],
                "body": "Opened and merged by the live suite.",
            },
        }
    )
    number = pull["number"]
    trash.later(lambda: world.github.pull_close(number))

    detail = await github.pulls_get.ainvoke({"owner": owner, "repo": repo, "pull_number": number})
    # changed_files and the counts exist only on this endpoint, never on a listing.
    assert detail["changed_files"] == 1
    assert detail["additions"] >= 1

    # `head` is 'user:branch' on the filter and a bare ref on the object, which is
    # the sort of asymmetry only the API can confirm.
    open_pulls = await github.pulls_list.ainvoke(
        {"owner": owner, "repo": repo, "state": "open", "head": f"{owner}:{branch}", "per_page": 10}
    )
    assert [p["number"] for p in open_pulls] == [number]
    assert open_pulls[0]["head"] == branch
    assert "changed_files" not in open_pulls[0]

    files = await github.pulls_list_files.ainvoke(
        {"owner": owner, "repo": repo, "pull_number": number, "per_page": 10}
    )
    assert [f["filename"] for f in files] == [path]

    renamed = await github.pulls_update.ainvoke(
        {"owner": owner, "repo": repo, "pull_number": number, "title": f"Live {run_tag}, renamed"}
    )
    assert renamed["title"] == f"Live {run_tag}, renamed"

    # COMMENT, not APPROVE: GitHub refuses to let an author approve their own
    # pull request, and this suite runs as the author of everything it makes.
    review = await github.pulls_create_review.ainvoke(
        {
            "owner": owner,
            "repo": repo,
            "pull_number": number,
            "event": "COMMENT",
            "body": "Reviewed by the live suite.",
        }
    )
    assert review["state"] == "COMMENTED"

    reviews = await github.pulls_list_reviews.ainvoke(
        {"owner": owner, "repo": repo, "pull_number": number, "per_page": 10}
    )
    assert review["id"] in [r["id"] for r in reviews]

    merged = await github.pulls_merge.ainvoke(
        {
            "owner": owner,
            "repo": repo,
            "pull_number": number,
            "merge_method": "squash",
            "commit_title": f"Live check {run_tag}",
        }
    )
    assert merged["merged"] is True

    # The file is now on the default branch, so teardown has to take it off.
    trash.later(
        lambda: world.github.content_delete(
            path=path, branch=base["default_branch"], message=f"live cleanup {run_tag}"
        )
    )

    on_main = await github.repos_get_content.ainvoke(
        {"owner": owner, "repo": repo, "path": path, "ref": base["default_branch"]}
    )
    assert on_main["content"] == body


async def test_a_reviewer_request_is_refused_by_identity_not_by_shape(
    needs, world, trash, run_tag, github_owner, sandbox_repo
):
    """``pulls_request_reviewers`` cannot be exercised on a one-account sandbox:
    GitHub will not let an author request themselves, and there is nobody else
    with push access.

    Asking anyway still proves what a live test can prove here — that the payload
    is built and accepted for parsing. A malformed one is a 400 with a different
    message; this is a 422 about *who*, which means the shape was fine.
    """
    needs("github")
    owner, repo = github_owner, sandbox_repo
    branch = f"live/{run_tag}-rev"

    await github.git_refs_create.ainvoke(
        {
            "owner": owner,
            "repo": repo,
            "ref": f"refs/heads/{branch}",
            "sha": await _head_sha(owner, repo, "main"),
        }
    )
    trash.later(lambda: world.github.branch_delete(branch))
    await github.repos_create_or_update_file.ainvoke(
        {
            "owner": owner,
            "repo": repo,
            "path": f"live/{run_tag}-rev.md",
            "message": f"live reviewer check {run_tag}",
            "content": "one line\n",
            "branch": branch,
        }
    )
    pull = await github.pulls_create.ainvoke(
        {
            "owner": owner,
            "repo": repo,
            "body": {"title": f"Live reviewer {run_tag}", "head": branch, "base": "main"},
        }
    )
    trash.later(lambda: world.github.pull_close(pull["number"]))

    me = await github.users_get_authenticated.ainvoke({})
    with pytest.raises(APIError) as refused:
        await github.pulls_request_reviewers.ainvoke(
            {
                "owner": owner,
                "repo": repo,
                "pull_number": pull["number"],
                "reviewers": [me["login"]],
            }
        )
    assert refused.value.status_code == 422
    assert "Review cannot be requested" in refused.value.body


# -----------------------------------------------------
# Issues
# -----------------------------------------------------


async def test_an_issue_is_opened_commented_on_and_closed(
    needs, world, trash, run_tag, github_owner, sandbox_repo
):
    """``issues_update`` takes its fields inside `body`, and a wrong nesting here
    is accepted by GitHub as an empty update rather than refused — so the test
    reads the change back instead of trusting the 200."""
    needs("github")
    owner, repo = github_owner, sandbox_repo

    issue = await github.issues_create.ainvoke(
        {
            "owner": owner,
            "repo": repo,
            "body": {
                "title": f"Live check {run_tag}",
                "body": "Opened by the live suite.",
            },
        }
    )
    number = issue["number"]
    trash.later(lambda: world.github.issue_close(number))

    found = await github.issues_get.ainvoke({"owner": owner, "repo": repo, "issue_number": number})
    assert found["title"] == f"Live check {run_tag}"
    assert found["body"] == "Opened by the live suite."

    comment = await github.issues_create_comment.ainvoke(
        {
            "owner": owner,
            "repo": repo,
            "issue_number": number,
            "body": {"body": f"Commented by the live suite, run {run_tag}."},
        }
    )
    assert comment["body"].endswith(f"run {run_tag}.")

    comments = await github.issues_list_comments.ainvoke(
        {"owner": owner, "repo": repo, "issue_number": number, "per_page": 10}
    )
    assert [c["id"] for c in comments] == [comment["id"]]

    closed = await github.issues_update.ainvoke(
        {
            "owner": owner,
            "repo": repo,
            "issue_number": number,
            "body": {"state": "closed", "state_reason": "not_planned"},
        }
    )
    assert closed["state"] == "closed"
    assert closed["state_reason"] == "not_planned"

    # The listing is not read-your-writes: an issue closed a second ago is
    # sometimes absent from it for a few seconds. `eventually` bounds the wait
    # rather than papering over a miss — the assertion below still has to hold.
    listing = await eventually(
        lambda: github.issues_list_for_repo.ainvoke(
            {"owner": owner, "repo": repo, "state": "closed", "per_page": 100}
        ),
        lambda items: number in [i["number"] for i in items],
        timeout=30.0,
    )
    assert number in [i["number"] for i in listing]


# -----------------------------------------------------
# Actions
# -----------------------------------------------------


async def test_the_workflow_run_filters_are_accepted(needs, github_owner, sandbox_repo):
    """The single ``status`` filter matches a run's status *or* its conclusion,
    which is why there is no ``conclusion`` parameter: GitHub would have ignored
    it silently rather than refuse it.

    ``failure`` is a conclusion and ``in_progress`` is a status, and both are
    valid in the same slot. The sandbox has no workflows, so the assertion is
    that neither spelling is a 422.
    """
    needs("github")
    for value in ("failure", "in_progress", "completed"):
        runs = await github.actions_list_workflow_runs.ainvoke(
            {
                "owner": github_owner,
                "repo": sandbox_repo,
                "status": value,
                "branch": "main",
                "exclude_pull_requests": True,
                "per_page": 5,
            }
        )
        assert "workflow_runs" in runs


async def test_rerunning_a_run_that_does_not_exist_is_a_404(
    needs, scope_skip, github_owner, sandbox_repo
):
    """``actions_rerun_workflow`` and ``actions_cancel_workflow_run`` need a run
    id, and a sandbox with no workflows has none. Cancelling someone's real run
    to get coverage is not a trade this suite makes.

    What is still worth pinning is the route: a 404 means the path template and
    the method reached GitHub's handler for this endpoint. A 405 or a 400 would
    mean they did not.

    ``enable_debug_logging`` is deliberately not passed. It is this pack's other
    lone-scalar body field, and sending it would exercise the runtime bug the
    Stripe suite already pins rather than anything about GitHub.
    """
    needs("github")
    missing = 1
    for tool in (github.actions_rerun_workflow, github.actions_cancel_workflow_run):
        with pytest.raises(APIError) as refused:
            await tool.ainvoke({"owner": github_owner, "repo": sandbox_repo, "run_id": missing})
        if refused.value.status_code == 403:
            scope_skip(refused.value, scope="Actions read and write")
        assert refused.value.status_code == 404


# -----------------------------------------------------
# Search, and the reads
# -----------------------------------------------------


async def test_search_accepts_its_qualifiers(needs, github_owner, sandbox_repo):
    """Three search endpoints, three different result envelopes.

    No count is asserted. GitHub's search index is not read-your-writes — code
    search only indexes default branches, and minutes behind — so a test that
    expected to find what this run just wrote would fail for a reason that has
    nothing to do with the pack.
    """
    needs("github")
    issues = await github.search_issues.ainvoke(
        {"q": f"repo:{github_owner}/{sandbox_repo} is:issue", "per_page": 5}
    )
    assert "items" in issues

    repos = await github.search_repositories.ainvoke(
        {"q": "topic:cli language:go", "sort": "stars", "order": "desc", "per_page": 5}
    )
    assert repos["items"]

    code = await github.search_code.ainvoke(
        {"q": f"harness repo:{github_owner}/{sandbox_repo}", "per_page": 5}
    )
    assert "items" in code


async def test_the_reads_are_accepted_as_declared(needs, github_owner, sandbox_repo):
    """``repos_list_for_authenticated_user`` is the one with a trap: ``type``
    together with ``visibility`` or ``affiliation`` is a 422 from GitHub, so the
    tool's own docstring says to pick one. Here it picks one."""
    needs("github")
    me = await github.users_get_authenticated.ainvoke({})
    assert me["login"] == github_owner

    mine = await github.repos_list_for_authenticated_user.ainvoke(
        {"visibility": "public", "affiliation": "owner", "sort": "updated", "per_page": 5}
    )
    assert any(r["full_name"] == f"{github_owner}/{sandbox_repo}" for r in mine)

    commits = await github.repos_list_commits.ainvoke(
        {"owner": github_owner, "repo": sandbox_repo, "sha": "main", "per_page": 3}
    )
    assert commits

    readme = await github.repos_get_content.ainvoke(
        {"owner": github_owner, "repo": sandbox_repo, "path": "README.md"}
    )
    assert readme["content"]

    root = await github.repos_get_content.ainvoke(
        {"owner": github_owner, "repo": sandbox_repo, "path": ""}
    )
    assert any(entry["name"] == "README.md" for entry in root)


async def test_writing_a_file_says_what_it_committed(
    needs, world, trash, run_tag, github_owner, sandbox_repo
):
    """A write that reports nothing is indistinguishable from one that did
    nothing, and the sha it withholds is the one the next update has to send.

    The PUT answers a different shape from the GET it shares a URL with, so it
    needs its own handler; running it through the read's projected every key away
    and returned ``{}``.
    """
    needs("github")
    owner, repo = github_owner, sandbox_repo
    path = f"live/{run_tag}-echo.md"

    trash.later(
        lambda: world.github.content_delete(
            path=path, branch="main", message=f"live cleanup {run_tag}"
        )
    )
    written = await github.repos_create_or_update_file.ainvoke(
        {
            "owner": owner,
            "repo": repo,
            "path": path,
            "message": f"live echo {run_tag}",
            "content": "one line\n",
            "branch": "main",
        }
    )
    assert written["commit"]["message"] == f"live echo {run_tag}"
    assert written["content"]["path"] == path
    # The sha this tool's own docstring tells the next write to send.
    assert written["content"]["sha"]

    # And it is the sha GitHub agrees the file has.
    on_disk = await github.repos_get_content.ainvoke({"owner": owner, "repo": repo, "path": path})
    assert on_disk["sha"] == written["content"]["sha"]
