"""
GitHub response trimming.

GitHub's objects are the widest in this repository. One issue carries a nested
``user``, ``assignee``, an ``assignees`` array, ``labels``, ``milestone``,
``reactions``, ``performed_via_github_app``, and roughly twenty ``*_url``
fields — a single issue is 4-6KB, and a page of thirty is a quarter of a
million characters. Almost none of it is actionable.

These handlers keep what an agent decides on and drop the rest. The invariant
they must preserve is the *length of the list*: GitHub pages by number and stops
when a page comes back shorter than ``per_page``, so a handler that filtered
items out would break paging. They project each item; they never drop one.
"""

from __future__ import annotations

from base64 import b64decode
from typing import Any, Callable, Dict, List, Optional, Sequence

from charter.text import decode_base64url

__all__ = [
    "trim_issues",
    "trim_written_content",
    "trim_pulls",
    "trim_repos",
    "trim_commits",
    "trim_comments",
    "trim_pull_files",
    "trim_content",
    "trim_user",
    "trim_branches",
    "trim_reviews",
    "trim_workflow_runs",
    "trim_code_search",
    "trim_jobs",
    "trim_workflows",
    "trim_artifacts",
    "trim_check_runs",
    "trim_check_suites",
    "trim_annotations",
    "trim_combined_status",
    "trim_run_usage",
    "trim_pending_deployments",
    "trim_secret_names",
    "tail_job_log",
    "tail_run_log_archive",
    "read_artifact_archive",
    "trim_review_comments",
    "trim_requested_reviewers",
    "trim_merged_check",
    "passthrough_diff",
    "trim_git_refs",
    "trim_git_commits",
    "trim_tree",
    "trim_blob",
    "trim_comparison",
    "trim_branch_protection",
    "trim_languages",
    "trim_contributors",
    "trim_tags",
    "trim_labels",
    "trim_milestones",
    "trim_issue_events",
    "trim_releases",
    "trim_release_assets",
    "trim_generated_notes",
    "trim_notifications",
    "trim_dependabot_alerts",
    "trim_code_scanning_alerts",
    "trim_secret_scanning_alerts",
    "trim_rate_limit",
    "trim_users",
]


def _login(value: Any) -> Optional[str]:
    """A GitHub user object -> just the login."""
    if isinstance(value, dict):
        return value.get("login")
    return None


def _label_names(value: Any) -> List[str]:
    """A labels array -> the names. GitHub allows bare strings here too."""
    if not isinstance(value, list):
        return []
    names = []
    for label in value:
        if isinstance(label, dict) and label.get("name"):
            names.append(label["name"])
        elif isinstance(label, str):
            names.append(label)
    return names


def _pick(obj: Dict[str, Any], fields: Sequence[str]) -> Dict[str, Any]:
    """Project one object onto ``fields``, dropping keys that are absent or null."""
    out: Dict[str, Any] = {}
    for field in fields:
        value = obj.get(field)
        if value not in (None, "", [], {}):
            out[field] = value
    return out


def _issue(obj: Dict[str, Any]) -> Dict[str, Any]:
    """One issue or pull request, reduced to what an agent acts on."""
    out = _pick(
        obj,
        (
            "number",
            "title",
            "state",
            "state_reason",
            "body",
            "html_url",
            "created_at",
            "updated_at",
            "closed_at",
            "comments",
            "draft",
        ),
    )
    if (author := _login(obj.get("user"))) is not None:
        out["author"] = author
    if assignees := [a for a in (_login(x) for x in obj.get("assignees") or []) if a]:
        out["assignees"] = assignees
    if labels := _label_names(obj.get("labels")):
        out["labels"] = labels
    if isinstance(obj.get("milestone"), dict):
        out["milestone"] = obj["milestone"].get("title")
    # The one reliable way to tell a pull request from an issue on the issues
    # endpoint, which returns both.
    if "pull_request" in obj:
        out["is_pull_request"] = True
    return out


def _pull(obj: Dict[str, Any]) -> Dict[str, Any]:
    """One pull request, including the branch pair and merge state."""
    out = _issue(obj)
    out.pop("is_pull_request", None)
    out.update(
        _pick(
            obj,
            (
                "merged",
                "mergeable",
                "mergeable_state",
                "merged_at",
                "additions",
                "deletions",
                "changed_files",
                "commits",
            ),
        )
    )
    for side in ("head", "base"):
        ref = obj.get(side)
        if isinstance(ref, dict) and ref.get("ref"):
            out[side] = ref["ref"]
    return out


def _repo(obj: Dict[str, Any]) -> Dict[str, Any]:
    """One repository."""
    out = _pick(
        obj,
        (
            "full_name",
            "description",
            "html_url",
            "private",
            "fork",
            "archived",
            "default_branch",
            "language",
            "stargazers_count",
            "forks_count",
            "open_issues_count",
            "topics",
            "pushed_at",
            "updated_at",
        ),
    )
    if (owner := _login(obj.get("owner"))) is not None:
        out["owner"] = owner
    return out


def _commit(obj: Dict[str, Any]) -> Dict[str, Any]:
    """One commit, flattened out of its nested ``commit`` object."""
    out = _pick(obj, ("sha", "html_url"))
    inner = obj.get("commit")
    if isinstance(inner, dict):
        out["message"] = inner.get("message")
        author = inner.get("author")
        if isinstance(author, dict):
            out["author"] = author.get("name")
            out["date"] = author.get("date")
    return {k: v for k, v in out.items() if v not in (None, "", [], {})}


# The keys GitHub wraps a list in. Most REST endpoints answer with a bare array;
# search uses `items`, and every Actions and Checks endpoint names its array
# after the thing in it. A handler that did not know a key would fall through to
# "project this object" and return `{}` for the whole page, so the set is
# declared once here and every collection handler reads it.
_ENVELOPE_KEYS = (
    "items",
    "workflow_runs",
    "jobs",
    "workflows",
    "artifacts",
    "secrets",
    "check_runs",
    "check_suites",
)


def _collection(project: Callable[[Dict[str, Any]], Dict[str, Any]]) -> Any:
    """Build a handler that projects a bare array or an enveloped one.

    GitHub answers list endpoints with a bare JSON array, search endpoints with
    ``{"total_count": N, "items": [...]}``, and Actions and Checks with an
    array named after its contents — see :data:`_ENVELOPE_KEYS`. Every shape
    goes through here, and the item count is preserved in all of them, because
    it is the paging signal.
    """

    async def handler(response: Any) -> Any:
        if isinstance(response, list):
            return [project(item) for item in response if isinstance(item, dict)]

        if isinstance(response, dict):
            for envelope in _ENVELOPE_KEYS:
                if not isinstance(response.get(envelope), list):
                    continue
                out: Dict[str, Any] = {
                    envelope: [
                        project(item)
                        for item in response[envelope]
                        if isinstance(item, dict)
                    ]
                }
                for key in ("total_count", "incomplete_results"):
                    if key in response:
                        out[key] = response[key]
                return out
            # A "get one" endpoint returns a bare object.
            return project(response)

        return response

    return handler


def _comment(obj: Dict[str, Any]) -> Dict[str, Any]:
    """One issue or pull-request comment.

    Measured on a real thread — 100 comments from a long cpython issue — the
    nested ``user`` object came to 119KB against 87KB for every word of every
    comment. The author is one login; the rest of that object is twenty
    ``*_url`` fields repeated a hundred times. With ``reactions``, ``node_id``
    and the three self-referential URLs dropped alongside it, the page falls
    from ~71,000 tokens to ~28,000 with nothing an agent reads removed.
    """
    out = _pick(obj, ("id", "body", "created_at", "updated_at", "html_url"))
    author = _login(obj.get("user"))
    if author:
        out["user"] = author
    # Says whether the commenter is the maintainer, the reporter or a passer-by,
    # which is most of what "who said this" is worth on a triage thread.
    if obj.get("author_association") not in (None, "", "NONE"):
        out["author_association"] = obj["author_association"]
    return out


# The envelope on a changed file: three URLs pointing at the same blob, plus the
# blob sha. `patch` is left whole — it is the diff, and an agent reviewing a
# change needs all of it — so this is a small saving on a response whose size is
# dominated by content that has to stay. See the note in the pack docstring.
_PULL_FILE_FIELDS = (
    "filename",
    "status",
    "additions",
    "deletions",
    "changes",
    "previous_filename",
    "patch",
)


def _pull_file(obj: Dict[str, Any]) -> Dict[str, Any]:
    """One file in a pull request's diff."""
    return _pick(obj, _PULL_FILE_FIELDS)


trim_issues = _collection(_issue)
trim_pulls = _collection(_pull)
trim_repos = _collection(_repo)
trim_commits = _collection(_commit)
trim_comments = _collection(_comment)
trim_pull_files = _collection(_pull_file)


async def trim_content(response: Any) -> Any:
    """Decode a file's contents, or reduce a directory listing to its entries.

    GitHub returns a file as base64 in ``content``, wrapped in ~10 URL fields.
    Handing the model the blob costs it a third more tokens than the file itself
    and it cannot read it; this decodes text, and says so plainly in the two
    cases where there is no text to hand over.

    Both of those cases are silent by default, which is why they are handled
    explicitly. A binary file decodes to replacement characters rather than
    raising, so a lenient decoder returns mojibake and calls it content; and a
    file over GitHub's 1MB JSON limit comes back with ``encoding: "none"`` and an
    empty ``content``, which projects down to a file object that looks empty
    rather than one that was never sent.
    """
    if isinstance(response, list):
        return [
            _pick(entry, ("name", "path", "type", "size"))
            for entry in response
            if isinstance(entry, dict)
        ]

    if not isinstance(response, dict):
        return response

    out = _pick(response, ("name", "path", "type", "size", "sha", "html_url"))
    encoding = response.get("encoding")

    if encoding == "base64" and isinstance(response.get("content"), str):
        try:
            # GitHub wraps the payload at 60 characters; the decoder tolerates
            # that. `strict` is what makes this a decision rather than a guess:
            # without it a PNG comes back as replacement characters and is
            # handed to the model as if it were the file.
            out["content"] = decode_base64url(response["content"], errors="strict")
        except Exception:
            out["content"] = _UNREADABLE.format(
                why="it is a binary file, not decodable as text"
            )
            _offer_download(out, response)
    elif encoding == "none":
        # 1-100MB: GitHub sends the metadata and withholds the bytes. Over
        # 100MB it does not serve this endpoint at all.
        # https://docs.github.com/en/rest/repos/contents#get-repository-content
        out["content"] = _UNREADABLE.format(
            why="GitHub does not return contents for files over 1MB on this endpoint"
        )
        _offer_download(out, response)

    return out


async def trim_written_content(response: Any) -> Any:
    """What a write to the contents endpoint reports back.

    A different shape from the read it shares a URL with: GitHub answers a PUT
    with ``{"content": {...file...}, "commit": {...}}``, where none of the file's
    keys are at the top level. Passing that through :func:`trim_content` projected
    every key away and returned ``{}`` — a write indistinguishable from a write
    that did nothing.

    Two things are worth keeping. The commit is the receipt. The file's new
    ``sha`` is the one the *next* write to that path has to send, per this tool's
    own docstring, and an agent that cannot read it here has to spend a second
    call re-reading the file it just wrote.
    """
    if not isinstance(response, dict):
        return response

    out: Dict[str, Any] = {}
    content = response.get("content")
    if isinstance(content, dict):
        out["content"] = _pick(content, ("name", "path", "sha", "size", "html_url"))

    commit = response.get("commit")
    if isinstance(commit, dict):
        entry = _pick(commit, ("sha", "message", "html_url"))
        author = commit.get("author")
        if isinstance(author, dict) and author.get("date"):
            entry["date"] = author["date"]
        out["commit"] = entry

    return out or response


_UNREADABLE = "<no content: {why}. Fetch download_url to read it.>"


def _offer_download(out: Dict[str, Any], response: Dict[str, Any]) -> None:
    """Keep the one URL that is actionable when the contents did not come through."""
    if response.get("download_url"):
        out["download_url"] = response["download_url"]


_USER_FIELDS = ("login", "name", "email", "company", "html_url", "type", "created_at")


async def trim_user(response: Any) -> Any:
    """The authenticated user, reduced to identity."""
    if not isinstance(response, dict):
        return response
    return _pick(response, _USER_FIELDS)


def _user(obj: Dict[str, Any]) -> Dict[str, Any]:
    """One user out of a *list* of them.

    Separate from :func:`trim_user` because the shapes are not the same thing:
    that one takes the single object `GET /user` returns, and running it over
    the search envelope projected every key away and returned `{}` — a search
    that reported no matches however many it found. Caught by the live check,
    which is the only place the two shapes meet.
    """
    return _pick(obj, _USER_FIELDS)


trim_users = _collection(_user)


def _branch(obj: Dict[str, Any]) -> Dict[str, Any]:
    """A branch, as its name and where it points.

    The raw object carries a `_links` block and a `commit` object with ~15 URL
    fields; what identifies a branch is its name, its head SHA and whether it is
    protected.
    """
    commit = obj.get("commit")
    out: Dict[str, Any] = {"name": obj.get("name")}
    if isinstance(commit, dict) and commit.get("sha"):
        out["sha"] = commit["sha"]
    if "protected" in obj:
        out["protected"] = obj["protected"]
    return out


def _review(obj: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        k: obj.get(k) for k in ("id", "state", "body", "submitted_at", "commit_id")
        if obj.get(k) is not None
    }
    user = obj.get("user")
    if isinstance(user, dict) and user.get("login"):
        out["user"] = user["login"]
    return out


def _workflow_run(obj: Dict[str, Any]) -> Dict[str, Any]:
    """One run, without the two pull-request blobs and forty URL fields.

    `conclusion` is passed through as whatever GitHub sent. It is an open string
    in their schema and real runs report values outside the documented set.
    """
    out: Dict[str, Any] = {
        k: obj.get(k)
        for k in (
            "id", "name", "status", "conclusion", "event", "head_branch",
            "head_sha", "run_number", "run_attempt", "created_at", "updated_at",
            "html_url",
        )
        if obj.get(k) is not None
    }
    actor = obj.get("actor")
    if isinstance(actor, dict) and actor.get("login"):
        out["actor"] = actor["login"]
    return out


def _code_hit(obj: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        k: obj.get(k) for k in ("name", "path", "sha", "html_url") if obj.get(k) is not None
    }
    repo = obj.get("repository")
    if isinstance(repo, dict) and repo.get("full_name"):
        out["repository"] = repo["full_name"]
    return out


trim_branches = _collection(_branch)
trim_reviews = _collection(_review)
trim_workflow_runs = _collection(_workflow_run)
trim_code_search = _collection(_code_hit)


# -----------------------------------------------------
# CI: jobs, logs, artifacts, checks
# -----------------------------------------------------


def _job(obj: Dict[str, Any]) -> Dict[str, Any]:
    """One job of a workflow run, with its steps reduced to the ones that matter.

    A job carries a `steps` array where every step repeats `status`,
    `conclusion`, `number`, `started_at` and `completed_at`. On a green job all
    of that says the same thing twice, so the steps are summarised: the failing
    ones by name, and a count of the rest. On a red job that summary *is* the
    answer — "which command failed" — for a fraction of the bytes.
    """
    out = _pick(
        obj,
        (
            "id",
            "name",
            "status",
            "conclusion",
            "started_at",
            "completed_at",
            "html_url",
            "workflow_name",
            "head_branch",
            "runner_name",
        ),
    )
    steps = obj.get("steps")
    if isinstance(steps, list):
        failed = [
            _pick(step, ("number", "name", "conclusion"))
            for step in steps
            if isinstance(step, dict)
            and step.get("conclusion") not in (None, "success", "skipped")
        ]
        if failed:
            out["failed_steps"] = failed
        out["steps_total"] = len(steps)
    return out


def _workflow(obj: Dict[str, Any]) -> Dict[str, Any]:
    """One workflow definition. `path` is the file an edit would go to."""
    return _pick(obj, ("id", "name", "path", "state", "updated_at", "html_url"))


def _artifact(obj: Dict[str, Any]) -> Dict[str, Any]:
    """One artifact. `expired` decides whether downloading it is worth a call."""
    out = _pick(
        obj,
        ("id", "name", "size_in_bytes", "created_at", "expires_at", "digest"),
    )
    # `expired` is False on a live artifact, which `_pick` would drop as falsy —
    # and "no expired key" reads as "unknown", not as "fine". Carried explicitly.
    if "expired" in obj:
        out["expired"] = bool(obj["expired"])
    return out


def _check_run(obj: Dict[str, Any]) -> Dict[str, Any]:
    """One check run, with the `output` block flattened to its text.

    `output` nests `title`, `summary` and `text` beside an `annotations_url` and
    a count; the count is what says whether `checks_list_annotations` is worth
    calling, so it is kept next to the summary rather than under it.
    """
    out = _pick(
        obj,
        (
            "id",
            "name",
            "status",
            "conclusion",
            "started_at",
            "completed_at",
            "html_url",
            "head_sha",
        ),
    )
    output = obj.get("output")
    if isinstance(output, dict):
        for key in ("title", "summary", "text"):
            if output.get(key):
                out[key] = output[key]
        if output.get("annotations_count"):
            out["annotations_count"] = output["annotations_count"]
    app = obj.get("app")
    if isinstance(app, dict) and app.get("slug"):
        out["app"] = app["slug"]
    return out


def _check_suite(obj: Dict[str, Any]) -> Dict[str, Any]:
    out = _pick(
        obj,
        (
            "id",
            "status",
            "conclusion",
            "head_branch",
            "head_sha",
            "created_at",
            "updated_at",
            "latest_check_runs_count",
        ),
    )
    app = obj.get("app")
    if isinstance(app, dict) and app.get("slug"):
        out["app"] = app["slug"]
    return out


def _annotation(obj: Dict[str, Any]) -> Dict[str, Any]:
    """One check annotation: a failure GitHub has already located.

    `blob_href` is dropped — it points at the same file the `path` and line
    already name, and it is the longest field in the object.
    """
    return _pick(
        obj,
        (
            "path",
            "start_line",
            "end_line",
            "start_column",
            "end_column",
            "annotation_level",
            "title",
            "message",
            "raw_details",
        ),
    )


def _commit_status(obj: Dict[str, Any]) -> Dict[str, Any]:
    return _pick(obj, ("context", "state", "description", "target_url", "updated_at"))


trim_jobs = _collection(_job)
trim_workflows = _collection(_workflow)
trim_artifacts = _collection(_artifact)
trim_check_runs = _collection(_check_run)
trim_check_suites = _collection(_check_suite)
trim_annotations = _collection(_annotation)


async def trim_combined_status(response: Any) -> Any:
    """The roll-up state, plus one line per context.

    Its own shape: an aggregate (`state`, `total_count`) and a paginated array
    (`statuses`) in the same object, wrapped in a whole `repository` object that
    the caller supplied the name of in the first place.
    """
    if not isinstance(response, dict):
        return response
    out = _pick(response, ("state", "sha", "total_count"))
    statuses = response.get("statuses")
    if isinstance(statuses, list):
        out["statuses"] = [
            _commit_status(item) for item in statuses if isinstance(item, dict)
        ]
    return out


async def trim_run_usage(response: Any) -> Any:
    """Billable time per runner OS, without the per-job breakdown.

    `billable` nests a `job_runs` array under each operating system, repeating
    every job id and duration a second time. The totals are the answer to "what
    did this run cost"; the per-job list is `actions_list_jobs_for_run`.
    """
    if not isinstance(response, dict):
        return response
    out: Dict[str, Any] = {}
    if response.get("run_duration_ms") is not None:
        out["run_duration_ms"] = response["run_duration_ms"]
    billable = response.get("billable")
    if isinstance(billable, dict):
        out["billable"] = {
            os_name: _pick(entry, ("total_ms", "jobs"))
            for os_name, entry in billable.items()
            if isinstance(entry, dict)
        }
    return out


async def trim_pending_deployments(response: Any) -> Any:
    """The environments a run is waiting on, and who can release them."""
    if not isinstance(response, list):
        return response
    out: List[Dict[str, Any]] = []
    for item in response:
        if not isinstance(item, dict):
            continue
        entry = _pick(item, ("wait_timer", "wait_timer_started_at"))
        if "current_user_can_approve" in item:
            entry["current_user_can_approve"] = bool(item["current_user_can_approve"])
        environment = item.get("environment")
        if isinstance(environment, dict):
            entry["environment_id"] = environment.get("id")
            entry["environment"] = environment.get("name")
        reviewers: List[str] = []
        for reviewer in item.get("reviewers") or []:
            if not isinstance(reviewer, dict):
                continue
            who = reviewer.get("reviewer")
            if isinstance(who, dict):
                name = who.get("login") or who.get("slug") or who.get("name")
                if name:
                    reviewers.append(name)
        if reviewers:
            entry["reviewers"] = reviewers
        out.append(entry)
    return out


def _secret(obj: Dict[str, Any]) -> Dict[str, Any]:
    """One secret: its name and when it changed.

    There is no value here to withhold — GitHub does not return one on this
    endpoint, encrypted or otherwise — so this projection is for size, not for
    safety. The safety is the endpoint's.
    """
    return _pick(obj, ("name", "created_at", "updated_at"))


trim_secret_names = _collection(_secret)


# -----------------------------------------------------
# Logs and archives: the two responses that are not JSON
# -----------------------------------------------------

# How much of a log is kept. A failing job's log is routinely megabytes and the
# answer is almost always in the last screen of it, so the tail is the default
# view and the matched lines are the index into what came before. Both are
# constants rather than parameters: a tool argument has to go somewhere on the
# wire, and GitHub has no query parameter for "give me less" — a field for it
# would be a field the model sets and nothing sends.
LOG_TAIL_LINES = 200
MAX_MATCHED_LINES = 40

# What a failure looks like in a CI log, across the runners and languages an
# agent will actually meet. Deliberately not a cleverer parser: this is an index
# to read the tail with, not a verdict, and the tail is right there beside it.
_FAILURE_MARKERS = (
    "##[error]",
    "error:",
    "error :",
    "failed:",
    " failed",
    "fatal:",
    "traceback (most recent call last)",
    "assertionerror",
    "exception:",
    "panic:",
    "segmentation fault",
    "npm err!",
    "e: ",
)


def _scan_log(text: str) -> Dict[str, Any]:
    """A log's tail, its size, and the lines that look like the failure.

    Returns the numbers too. "You are seeing the last 200 of 48,000 lines" is
    the difference between a model that knows to ask for a different job and one
    that concludes the log was short.
    """
    lines = text.splitlines()
    matched = [
        f"{number}: {line.strip()[:500]}"
        for number, line in enumerate(lines, start=1)
        if any(marker in line.lower() for marker in _FAILURE_MARKERS)
    ]
    out: Dict[str, Any] = {
        "total_lines": len(lines),
        "tail_lines": min(len(lines), LOG_TAIL_LINES),
        "tail": "\n".join(lines[-LOG_TAIL_LINES:]),
    }
    if matched:
        out["matched_lines"] = matched[-MAX_MATCHED_LINES:]
        out["matched_total"] = len(matched)
    return out


async def tail_job_log(response: Any) -> Any:
    """A job's plain-text log, reduced to its tail and its failure lines.

    The whole point of the tool and the whole risk of it. GitHub serves a job
    log as a plain text file behind a one-minute redirect, and the file is as
    long as the job was talkative — inlining it verbatim would undo every
    projection in this pack in a single call.

    The unhappy path is named rather than left to the default: if the payload
    did not arrive as text it is reported as that, with its type and size,
    instead of being handed over as something that looks like a log.
    """
    if not isinstance(response, dict):
        return response
    if "raw_base64" in response:
        return {
            "error": (
                "The log did not arrive as text. Expected a plain text file; got "
                f"{response.get('content_type')}."
            ),
            "size_bytes": response.get("size_bytes"),
        }
    raw = response.get("raw")
    if not isinstance(raw, str):
        return response
    if not raw.strip():
        return {"total_lines": 0, "tail": "", "note": "The log is empty."}
    return _scan_log(raw)


def _open_zip(response: Dict[str, Any]) -> Any:
    """The archive in a response, or ``None`` if there is not one.

    ``zipfile`` and ``io`` are stdlib; nothing here reaches for a dependency.
    """
    import io
    import zipfile

    encoded = response.get("raw_base64")
    if not isinstance(encoded, str):
        return None
    try:
        return zipfile.ZipFile(io.BytesIO(b64decode(encoded)))
    except Exception:
        return None


async def tail_run_log_archive(response: Any) -> Any:
    """A whole run's logs: one tail per job, out of the ZIP GitHub sends.

    This endpoint's payload is an archive, not text — GitHub's own word is
    "an archive of log files" — so the sibling handler's decode would have
    produced mojibake. The archive holds one text file per job, which makes this
    the one call that covers a run whose failure could be in any of them.

    Directory entries and the per-step files GitHub also packs in are skipped:
    the per-job file at the archive root is the same content, once.
    """
    if not isinstance(response, dict):
        return response
    archive = _open_zip(response)
    if archive is None:
        return {
            "error": "The run log archive did not arrive as a readable ZIP.",
            "content_type": response.get("content_type"),
            "size_bytes": response.get("size_bytes"),
        }

    jobs: List[Dict[str, Any]] = []
    with archive:
        for info in archive.infolist():
            # The per-job logs sit at the archive root; everything under a
            # directory is the same content split per step.
            if info.is_dir() or "/" in info.filename:
                continue
            try:
                text = archive.read(info.filename).decode("utf-8", errors="replace")
            except Exception:
                continue
            entry: Dict[str, Any] = {"job": info.filename}
            entry.update(_scan_log(text))
            jobs.append(entry)

    if not jobs:
        return {
            "jobs": [],
            "note": "The archive held no job logs at its root.",
            "size_bytes": response.get("size_bytes"),
        }
    return {"jobs": jobs, "job_count": len(jobs)}


# An artifact is an arbitrary archive and there is no upper bound on what it
# holds, so its contents are admitted under a budget rather than in full.
MAX_ARTIFACT_ENTRY_BYTES = 64_000
MAX_ARTIFACT_TEXT_BYTES = 200_000


async def read_artifact_archive(response: Any) -> Any:
    """What is inside a downloaded artifact, and the small text of it.

    An artifact is whatever the workflow chose to upload: a JUnit report, a
    coverage summary, or a 400MB binary. Handing the archive to a model is not
    an option for the second case and is not necessary for the first, so this
    reads the ZIP's own index — every entry's name and size, which is cheap and
    complete — and then admits the text entries under a budget.

    An entry is skipped rather than truncated when it is too big, and said to be
    skipped, because half a JSON file read as a whole one is worse than none.
    """
    if not isinstance(response, dict):
        return response
    archive = _open_zip(response)
    if archive is None:
        return {
            "error": "The artifact did not arrive as a readable ZIP.",
            "content_type": response.get("content_type"),
            "size_bytes": response.get("size_bytes"),
        }

    entries: List[Dict[str, Any]] = []
    files: Dict[str, str] = {}
    budget = MAX_ARTIFACT_TEXT_BYTES
    skipped: List[str] = []

    with archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            entries.append({"name": info.filename, "size_bytes": info.file_size})
            if info.file_size > MAX_ARTIFACT_ENTRY_BYTES or info.file_size > budget:
                skipped.append(info.filename)
                continue
            try:
                # `strict`, so a binary entry is skipped rather than handed over
                # as replacement characters that read as content.
                text = archive.read(info.filename).decode("utf-8")
            except Exception:
                skipped.append(info.filename)
                continue
            files[info.filename] = text
            budget -= info.file_size

    out: Dict[str, Any] = {
        "entries": entries,
        "entry_count": len(entries),
        "size_bytes": response.get("size_bytes"),
    }
    if files:
        out["files"] = files
    if skipped:
        out["not_inlined"] = skipped
        out["not_inlined_note"] = (
            "Too large to inline, or not UTF-8 text. Their names and sizes are in "
            "`entries`."
        )
    return out


# -----------------------------------------------------
# Code review
# -----------------------------------------------------


def _review_comment(obj: Dict[str, Any]) -> Dict[str, Any]:
    """One comment on a line of a diff.

    Keeps the placement — file, line, side — because that is what the comment
    *is*; a review comment without its coordinates is an anonymous remark. The
    `diff_hunk` GitHub sends beside it is dropped: it is a copy of a diff the
    caller either has or can fetch, repeated on every comment in the thread.
    """
    out = _pick(
        obj,
        (
            "id",
            "body",
            "path",
            "line",
            "original_line",
            "start_line",
            "side",
            "start_side",
            "subject_type",
            "commit_id",
            "in_reply_to_id",
            "pull_request_review_id",
            "created_at",
            "updated_at",
            "html_url",
        ),
    )
    if (author := _login(obj.get("user"))) is not None:
        out["user"] = author
    if obj.get("author_association") not in (None, "", "NONE"):
        out["author_association"] = obj["author_association"]
    # An outdated comment has a null `line`: the code it was written against is
    # gone. Saying so is the difference between "no line" and "no longer there".
    if obj.get("line") is None and obj.get("original_line") is not None:
        out["outdated"] = True
    return out


trim_review_comments = _collection(_review_comment)


async def trim_requested_reviewers(response: Any) -> Any:
    """Who is still being waited on, as two lists of names.

    GitHub answers with ``{"users": [...], "teams": [...]}`` of full user and
    team objects. What an agent does with this is nudge someone, so the logins
    and the slugs are the whole of it.
    """
    if not isinstance(response, dict):
        return response
    out: Dict[str, Any] = {}
    users = [_login(u) for u in response.get("users") or [] if isinstance(u, dict)]
    if any(users):
        out["users"] = [u for u in users if u]
    teams = [
        t.get("slug") for t in response.get("teams") or [] if isinstance(t, dict)
    ]
    if any(teams):
        out["teams"] = [t for t in teams if t]
    return out


async def trim_merged_check(response: Any) -> Any:
    """The answer a bodiless endpoint gives.

    ``pulls_check_merged`` reports in its status line: 204 for merged, 404 for
    not. Charter raises on the 404, so reaching this handler at all is the
    "yes", and the empty body would otherwise be returned as ``{}`` — which
    reads as "nothing found" rather than as the affirmative it is.
    """
    return {"merged": True}


async def passthrough_diff(response: Any) -> Any:
    """A unified diff, with its size stated beside it.

    The one handler in this pack that does not reduce anything: a diff is the
    content, and trimming it would be trimming the change. What it adds is the
    measurement, so that a model reading 40,000 lines of vendored lockfile knows
    that is what it is reading and can switch to ``pulls_list_files``.
    """
    if not isinstance(response, dict):
        return response
    if "raw_base64" in response:
        return {
            "error": (
                "The diff did not arrive as text. Got "
                f"{response.get('content_type')}."
            ),
            "size_bytes": response.get("size_bytes"),
        }
    diff = response.get("raw")
    if not isinstance(diff, str):
        return response
    lines = diff.splitlines()
    return {
        "diff": diff,
        "lines": len(lines),
        "files_changed": sum(1 for line in lines if line.startswith("diff --git ")),
    }


# -----------------------------------------------------
# The Git object store
# -----------------------------------------------------


def _git_ref(obj: Dict[str, Any]) -> Dict[str, Any]:
    """One reference, flattened to what it points at.

    The `object` wrapper carries a type, a SHA and a URL; the SHA is the answer
    to the only question this endpoint is asked — what is the head of this
    branch — so it comes up a level.
    """
    out = _pick(obj, ("ref",))
    target = obj.get("object")
    if isinstance(target, dict):
        out["sha"] = target.get("sha")
        out["type"] = target.get("type")
    return {k: v for k, v in out.items() if v is not None}


def _git_commit(obj: Dict[str, Any]) -> Dict[str, Any]:
    """One Git commit object: message, tree, parents.

    `verification` is kept only when it says something — an unsigned commit
    reports `verified: false` with a `reason` of "unsigned" and two null fields,
    which is four keys to say nothing.
    """
    out = _pick(obj, ("sha", "message", "html_url"))
    tree = obj.get("tree")
    if isinstance(tree, dict) and tree.get("sha"):
        out["tree"] = tree["sha"]
    parents = [
        p["sha"] for p in obj.get("parents") or [] if isinstance(p, dict) and p.get("sha")
    ]
    if parents:
        out["parents"] = parents
    for role in ("author", "committer"):
        who = obj.get(role)
        if isinstance(who, dict) and who.get("name"):
            out[role] = who.get("name")
            if who.get("date"):
                out[f"{role}_date"] = who["date"]
    verification = obj.get("verification")
    if isinstance(verification, dict) and verification.get("verified"):
        out["verified"] = True
    return out


def _tree_entry(obj: Dict[str, Any]) -> Dict[str, Any]:
    return _pick(obj, ("path", "mode", "type", "sha", "size"))


async def trim_tree(response: Any) -> Any:
    """A tree's entries, and whether GitHub had to cut the list short.

    `truncated` is the one field here that must never be dropped. GitHub sets it
    when a recursive read exceeded 100,000 entries or 7 MB, and a caller that
    does not see it reads a partial tree as a complete one — then writes a
    commit from it.
    """
    if not isinstance(response, dict):
        return response
    out = _pick(response, ("sha", "url"))
    out.pop("url", None)
    entries = response.get("tree")
    if isinstance(entries, list):
        out["tree"] = [_tree_entry(e) for e in entries if isinstance(e, dict)]
        out["entry_count"] = len(entries)
    # Explicitly, including when false: "no truncated key" reads as "complete",
    # and only one of those two is something GitHub actually said.
    out["truncated"] = bool(response.get("truncated"))
    return out


async def trim_blob(response: Any) -> Any:
    """A blob, decoded to text where it is text.

    The same two unhappy paths as `trim_content`, and for the same reason: a
    lenient decode turns a binary file into replacement characters that read as
    content, and GitHub's own 1MB ceiling is reported as `encoding: "none"`
    rather than as an error.
    """
    if not isinstance(response, dict):
        return response
    out = _pick(response, ("sha", "size"))
    encoding = response.get("encoding")
    if encoding == "base64" and isinstance(response.get("content"), str):
        try:
            out["content"] = decode_base64url(response["content"], errors="strict")
        except Exception:
            out["content"] = _UNREADABLE.format(
                why="it is a binary blob, not decodable as text"
            )
    elif encoding == "none":
        out["content"] = _UNREADABLE.format(
            why="GitHub does not return contents for blobs over 1MB on this endpoint"
        )
    return out


async def trim_comparison(response: Any) -> Any:
    """What is in one ref and not the other.

    `status`, `ahead_by` and `behind_by` are the summary an agent decides on;
    the commits and files are the detail, projected the same way they are
    everywhere else in this pack.
    """
    if not isinstance(response, dict):
        return response
    out = _pick(response, ("status", "ahead_by", "behind_by", "total_commits", "html_url"))
    for side in ("base_commit", "merge_base_commit"):
        entry = response.get(side)
        if isinstance(entry, dict) and entry.get("sha"):
            out[side] = entry["sha"]
    commits = response.get("commits")
    if isinstance(commits, list):
        out["commits"] = [_commit(c) for c in commits if isinstance(c, dict)]
    files = response.get("files")
    if isinstance(files, list):
        out["files"] = [_pull_file(f) for f in files if isinstance(f, dict)]
    return out


async def trim_branch_protection(response: Any) -> Any:
    """A branch's rules, as the reasons a write could be refused.

    The raw object is a dozen nested `{"enabled": bool}` wrappers and several
    URL-bearing sub-objects. What a caller needs is the list of conditions, so
    each toggle is flattened to a boolean and the checks are named.
    """
    if not isinstance(response, dict):
        return response
    out: Dict[str, Any] = {}
    for key in (
        "required_linear_history",
        "allow_force_pushes",
        "allow_deletions",
        "block_creations",
        "required_conversation_resolution",
        "required_signatures",
        "lock_branch",
        "allow_fork_syncing",
        "enforce_admins",
    ):
        entry = response.get(key)
        if isinstance(entry, dict) and "enabled" in entry:
            out[key] = bool(entry["enabled"])
    checks = response.get("required_status_checks")
    if isinstance(checks, dict):
        summary = _pick(checks, ("strict", "contexts"))
        if summary:
            out["required_status_checks"] = summary
    reviews = response.get("required_pull_request_reviews")
    if isinstance(reviews, dict):
        out["required_pull_request_reviews"] = _pick(
            reviews,
            (
                "required_approving_review_count",
                "dismiss_stale_reviews",
                "require_code_owner_reviews",
                "require_last_push_approval",
            ),
        )
    return out


async def trim_languages(response: Any) -> Any:
    """Languages and their byte counts, passed through.

    An object keyed by language name, which is already the smallest form of
    itself — there is nothing here to project, and a handler that reshaped it
    would only make it harder to read.
    """
    return response


def _contributor(obj: Dict[str, Any]) -> Dict[str, Any]:
    out = _pick(obj, ("login", "contributions", "type"))
    # An anonymous contributor has no login; the email is the only identity.
    if not out.get("login") and obj.get("email"):
        out["email"] = obj["email"]
        out["name"] = obj.get("name")
    return {k: v for k, v in out.items() if v is not None}


def _tag(obj: Dict[str, Any]) -> Dict[str, Any]:
    out = _pick(obj, ("name",))
    commit = obj.get("commit")
    if isinstance(commit, dict) and commit.get("sha"):
        out["sha"] = commit["sha"]
    return out


trim_git_refs = _collection(_git_ref)
trim_git_commits = _collection(_git_commit)
trim_contributors = _collection(_contributor)
trim_tags = _collection(_tag)


# -----------------------------------------------------
# Issue metadata: labels, milestones, history
# -----------------------------------------------------


def _label(obj: Dict[str, Any]) -> Dict[str, Any]:
    """One label. `default` and `id` are GitHub's bookkeeping; the name is the
    handle every other endpoint takes."""
    return _pick(obj, ("name", "color", "description"))


def _milestone(obj: Dict[str, Any]) -> Dict[str, Any]:
    out = _pick(
        obj,
        (
            "number",
            "title",
            "description",
            "state",
            "open_issues",
            "closed_issues",
            "due_on",
            "html_url",
        ),
    )
    if (creator := _login(obj.get("creator"))) is not None:
        out["creator"] = creator
    return out


def _issue_event(obj: Dict[str, Any]) -> Dict[str, Any]:
    """One event from an issue's history or timeline.

    A discriminated union of roughly thirty shapes, each carrying whichever of
    `label`, `assignee`, `milestone`, `rename` or `source` its kind uses. Rather
    than modelling all of them, the fields that are ever populated are picked
    and flattened to their names — which is what they say — and `event` is
    passed through as whatever GitHub sent, because the set grows.
    """
    out = _pick(obj, ("event", "created_at", "commit_id", "body", "state"))
    for role in ("actor", "assignee", "assigner", "requested_reviewer", "user"):
        if (who := _login(obj.get(role))) is not None:
            out[role] = who
    label = obj.get("label")
    if isinstance(label, dict) and label.get("name"):
        out["label"] = label["name"]
    milestone = obj.get("milestone")
    if isinstance(milestone, dict) and milestone.get("title"):
        out["milestone"] = milestone["title"]
    rename = obj.get("rename")
    if isinstance(rename, dict):
        out["rename"] = _pick(rename, ("from", "to"))
    source = obj.get("source")
    if isinstance(source, dict):
        issue = source.get("issue")
        if isinstance(issue, dict):
            out["source"] = _pick(issue, ("number", "title", "html_url"))
    return out


trim_labels = _collection(_label)
trim_milestones = _collection(_milestone)
trim_issue_events = _collection(_issue_event)


# -----------------------------------------------------
# Releases
# -----------------------------------------------------


def _release(obj: Dict[str, Any]) -> Dict[str, Any]:
    """One release.

    `body` is the changelog and stays whole — it is the content. What goes is
    the six `*_url` fields, the author object, and the `assets` array's own
    twenty-field entries, which are summarised to name and size.
    """
    out = _pick(
        obj,
        (
            "id",
            "tag_name",
            "name",
            "body",
            "target_commitish",
            "created_at",
            "published_at",
            "html_url",
        ),
    )
    for flag in ("draft", "prerelease"):
        if flag in obj:
            out[flag] = bool(obj[flag])
    if (author := _login(obj.get("author"))) is not None:
        out["author"] = author
    assets = obj.get("assets")
    if isinstance(assets, list) and assets:
        out["assets"] = [_release_asset(a) for a in assets if isinstance(a, dict)]
    return out


def _release_asset(obj: Dict[str, Any]) -> Dict[str, Any]:
    return _pick(
        obj,
        (
            "id",
            "name",
            "label",
            "state",
            "content_type",
            "size",
            "download_count",
            "browser_download_url",
        ),
    )


trim_releases = _collection(_release)
trim_release_assets = _collection(_release_asset)


async def trim_generated_notes(response: Any) -> Any:
    """The generated name and body, which is all this endpoint returns."""
    if not isinstance(response, dict):
        return response
    return _pick(response, ("name", "body"))


# -----------------------------------------------------
# Notifications and security alerts
# -----------------------------------------------------


def _notification(obj: Dict[str, Any]) -> Dict[str, Any]:
    """One notification thread, flattened to what it is about and why.

    `reason` and `subject.url` are the pair that matter: the reason says whether
    this needs the agent (`mention`, `review_requested`, `assign`) and the URL
    says what to fetch next. The `repository` object is thirty fields for one
    name.
    """
    out = _pick(obj, ("id", "reason", "updated_at"))
    if "unread" in obj:
        out["unread"] = bool(obj["unread"])
    subject = obj.get("subject")
    if isinstance(subject, dict):
        out["title"] = subject.get("title")
        out["type"] = subject.get("type")
        out["url"] = subject.get("url")
    repository = obj.get("repository")
    if isinstance(repository, dict) and repository.get("full_name"):
        out["repository"] = repository["full_name"]
    return {k: v for k, v in out.items() if v is not None}


def _dependabot_alert(obj: Dict[str, Any]) -> Dict[str, Any]:
    """One Dependabot alert, reduced to the decision it asks for.

    The raw object nests a whole advisory — identifiers, references, CVSS
    vectors, the full CWE list and a markdown description that runs to
    kilobytes. What triage needs is which package, how bad, and whether there is
    a version to move to.
    """
    out = _pick(obj, ("number", "state", "created_at", "updated_at", "html_url"))
    dependency = obj.get("dependency")
    if isinstance(dependency, dict):
        package = dependency.get("package")
        if isinstance(package, dict):
            out["package"] = package.get("name")
            out["ecosystem"] = package.get("ecosystem")
        for key in ("manifest_path", "scope", "relationship"):
            if dependency.get(key):
                out[key] = dependency[key]
    advisory = obj.get("security_advisory")
    if isinstance(advisory, dict):
        out["severity"] = advisory.get("severity")
        out["summary"] = advisory.get("summary")
        out["ghsa_id"] = advisory.get("ghsa_id")
        cve = advisory.get("cve_id")
        if cve:
            out["cve_id"] = cve
    vulnerability = obj.get("security_vulnerability")
    if isinstance(vulnerability, dict):
        patched = vulnerability.get("first_patched_version")
        if isinstance(patched, dict) and patched.get("identifier"):
            out["first_patched_version"] = patched["identifier"]
        if vulnerability.get("vulnerable_version_range"):
            out["vulnerable_version_range"] = vulnerability["vulnerable_version_range"]
    for key in ("dismissed_reason", "dismissed_comment"):
        if obj.get(key):
            out[key] = obj[key]
    return {k: v for k, v in out.items() if v is not None}


def _code_scanning_alert(obj: Dict[str, Any]) -> Dict[str, Any]:
    """One code scanning alert, with the rule and the place it fired."""
    out = _pick(
        obj,
        ("number", "state", "created_at", "updated_at", "html_url", "dismissed_reason"),
    )
    rule = obj.get("rule")
    if isinstance(rule, dict):
        out["rule"] = rule.get("id")
        out["severity"] = rule.get("security_severity_level") or rule.get("severity")
        out["description"] = rule.get("description")
    tool = obj.get("tool")
    if isinstance(tool, dict) and tool.get("name"):
        out["tool"] = tool["name"]
    instance = obj.get("most_recent_instance")
    if isinstance(instance, dict):
        location = instance.get("location")
        if isinstance(location, dict):
            out["location"] = _pick(
                location, ("path", "start_line", "end_line", "start_column", "end_column")
            )
        message = instance.get("message")
        if isinstance(message, dict) and message.get("text"):
            out["message"] = message["text"]
        if instance.get("ref"):
            out["ref"] = instance["ref"]
    return {k: v for k, v in out.items() if v is not None}


def _secret_scanning_alert(obj: Dict[str, Any]) -> Dict[str, Any]:
    """One secret scanning alert — without the secret.

    The `secret` field is dropped here unconditionally, whatever the request
    asked for. A leaked credential is not something an agent needs in order to
    triage, rotate or close an alert, and a response handler is the last place
    it can be kept out of a context window. What is kept is enough to act:
    which pattern, which provider, whether it is still valid, and where to look.
    """
    out = _pick(
        obj,
        (
            "number",
            "state",
            "resolution",
            "secret_type",
            "secret_type_display_name",
            "provider_slug",
            "validity",
            "created_at",
            "updated_at",
            "resolved_at",
            "html_url",
        ),
    )
    if (who := _login(obj.get("resolved_by"))) is not None:
        out["resolved_by"] = who
    for flag in ("publicly_leaked", "multi_repo", "push_protection_bypassed"):
        if obj.get(flag):
            out[flag] = True
    return out


trim_notifications = _collection(_notification)
trim_dependabot_alerts = _collection(_dependabot_alert)
trim_code_scanning_alerts = _collection(_code_scanning_alert)
trim_secret_scanning_alerts = _collection(_secret_scanning_alert)


async def trim_rate_limit(response: Any) -> Any:
    """The budgets that are being spent, without the ones that are not.

    GitHub reports a dozen resources, most of which no pack here touches, plus
    a top-level `rate` key it says is "closing down" and which duplicates
    `core`. What is kept is every resource with something spent against it,
    plus `core` and `search` whether or not they have been touched, since those
    are the two this pack uses.
    """
    if not isinstance(response, dict):
        return response
    resources = response.get("resources")
    if not isinstance(resources, dict):
        return response
    out: Dict[str, Any] = {}
    for name, budget in resources.items():
        if not isinstance(budget, dict):
            continue
        if name in ("core", "search") or budget.get("used"):
            out[name] = _pick(budget, ("limit", "remaining", "reset", "used"))
    return out
