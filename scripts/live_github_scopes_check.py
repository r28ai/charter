#!/usr/bin/env python
"""Does every GitHub tool declare what GitHub itself says the endpoint accepts?

Deliberately not a test: the suite is offline by rule. GitHub answers every call
made with a classic token with ``X-Accepted-OAuth-Scopes``, "the scopes that the
action checks for" (docs.github.com, Scopes for OAuth apps), whatever the token
itself holds. So a classic token with **no scopes at all** is enough to read the
answer for every tool, and it cannot change anything: GitHub refuses it every
write, even on a public repository.

    GITHUB_SCOPE_PROBE_TOKEN=ghp_... uv run python scripts/live_github_scopes_check.py --owner nqme-archive

Create the token at github.com/settings/tokens/new with every box unticked.

``--kind fine_grained`` asks the same of the permissions a GitHub App or a
fine-grained token carries. GitHub names them in ``X-Accepted-GitHub-Permissions``
on every answer to such a token, a 404 included, so any fine-grained token will
do, whatever it holds. Every repository call is aimed at a repository that does
not exist, so nothing it sends can change anything, and the two notification
writes are not sent at all (GitHub serves notifications to no fine-grained
token). The run stops if a write ever comes back as a success.

    GITHUB_PERMISSION_PROBE_TOKEN=github_pat_... uv run python scripts/live_github_scopes_check.py \\
        --owner nqme-archive --kind fine_grained
 Every
probe targets a repository that does not exist under ``<owner>``, or an id that
does not exist. Where GitHub names no scope for a call (the public-profile read,
the searches), the row says so rather than counting as agreement. Prints a
row per tool and exits non-zero when a declaration offers a scope GitHub does not
accept, or misses one it requires. Prints no token.
"""

from __future__ import annotations

import argparse
import asyncio
import itertools
import json
import os
import sys
from typing import Any

import httpx

from charter import APIError, CharterError, Tool, ToolValidationError
from charter.auth import AnyOf, StaticTokenProvider, Unavailable
from charter.packs import github

# Each tool is asked about twice, because GitHub answers differently by context
# (2026-10-24). About a repository that does not exist it cannot tell whether the
# repository would be private, so it names the scope a private one needs, and stops
# there: the security-alert endpoints name only `repo`. About the public
# harness-sandbox it checks no scope for most calls and names none, but the
# security-alert endpoints name everything they accept, `security_events` included.
# A scope GitHub names in either context is one it accepts. A missing repository
# also leaves every write without a target; the public one is refused writes
# because the token holds no scope.
REPOS = ("charter-scope-probe-no-such-repo", "harness-sandbox")
REPO = REPOS[0]
MISSING_NUMBER = 999999
MISSING_SHA = "0" * 40


def _placeholder(name: str, schema: dict[str, Any], owner: str) -> Any:
    """A value the tool accepts for a required argument, aimed at nothing that exists."""
    if name == "owner":
        return owner
    if name == "repo":
        return REPO
    if "enum" in schema:
        return schema["enum"][0]
    kind = schema.get("type")
    if kind == "integer":
        return MISSING_NUMBER
    if kind == "boolean":
        return False
    if kind == "array":
        return []
    if kind == "object":
        return {}
    if name in ("sha", "commit_sha", "tree_sha", "file_sha", "head_sha", "base_tree"):
        return MISSING_SHA
    if name in ("ref", "branch", "basehead", "head", "base"):
        return "charter-scope-probe-missing"
    if name == "q":
        return f"repo:{owner}/{REPO} charter-scope-probe"
    return "charter-scope-probe"


# Where a placeholder would break one of the tool's own rules. Each still aims at
# nothing that exists: a pull request, issue or commit that is not there.
OVERRIDES: dict[str, dict[str, Any]] = {
    "pulls_create": {
        "body": {
            "title": "charter scope probe",
            "head": "charter-scope-probe-missing",
            "base": "charter-scope-probe-missing",
        }
    },
    "pulls_request_reviewers": {"reviewers": ["charter-scope-probe"]},
    "git_refs_create": {"ref": "refs/heads/charter-scope-probe-missing"},
    "pulls_create_review_comment": {"subjectType": "file"},
    "git_trees_create": {
        "tree": [{"path": "x", "mode": "100644", "type": "blob", "sha": MISSING_SHA}]
    },
    "git_commits_create": {"tree": MISSING_SHA, "parents": [MISSING_SHA]},
    "repos_compare_commits": {"basehead": "charter-scope-probe-a...charter-scope-probe-b"},
    "issues_add_labels": {"labels": ["charter-scope-probe"]},
    "issues_add_assignees": {"assignees": ["charter-scope-probe"]},
    "issues_remove_assignees": {"assignees": ["charter-scope-probe"]},
}


def _merge(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in extra.items():
        out[key] = (
            _merge(out[key], value)
            if isinstance(value, dict) and isinstance(out.get(key), dict)
            else value
        )
    return out


def _args(tool: Tool, owner: str) -> dict[str, Any]:
    schema = tool.to_json_schema()["parameters"]
    defs = schema.get("$defs", {})

    def resolve(s: dict[str, Any]) -> dict[str, Any]:
        while "$ref" in s:
            s = defs[s["$ref"].split("/")[-1]]
        return s

    def fill(s: dict[str, Any]) -> dict[str, Any]:
        s = resolve(s)
        out = {}
        for name in s.get("required", []):
            prop = resolve(s["properties"][name])
            if prop.get("type") == "object" and "properties" in prop:
                out[name] = fill(prop)
            else:
                out[name] = _placeholder(name, prop, owner)
        return out

    return _merge(fill(schema), OVERRIDES.get(tool.name, {}))


def _options(requirement) -> tuple[str, ...]:
    if isinstance(requirement, Unavailable):
        return ()
    return requirement.options if isinstance(requirement, AnyOf) else (requirement,)


async def main(owner: str) -> int:
    token = os.environ.get("GITHUB_SCOPE_PROBE_TOKEN", "")
    if not token.startswith("ghp_"):
        sys.exit("GITHUB_SCOPE_PROBE_TOKEN must be a classic token (ghp_...) with no scopes ticked")
    github.configure(StaticTokenProvider(token))
    seen: dict[str, str] = {}

    async def record(response: httpx.Response) -> None:
        held = response.headers.get("x-oauth-scopes")
        if held:
            raise SystemExit(f"the probe token holds scopes ({held}); make one with none ticked")
        seen["accepted"] = response.headers.get("x-accepted-oauth-scopes", "")
        seen["status"] = str(response.status_code)

    # Before any tool runs, a read-only call: the token must hold no scope at all,
    # which is what makes every write below a refusal rather than a change.
    async with httpx.AsyncClient(timeout=30) as plain:
        me = await plain.get(
            "https://api.github.com/user", headers={"Authorization": f"Bearer {token}"}
        )
    if me.status_code != 200 or me.headers.get("x-oauth-scopes", "").strip():
        sys.exit(
            f"refusing: GET /user answered {me.status_code} with scopes "
            f"{me.headers.get('x-oauth-scopes')!r}; the probe token must hold none"
        )
    print(f"probe token belongs to {me.json().get('login')} and holds no scopes")

    named: dict[str, set[str]] = {t.name: set() for t in github.TOOLS}
    statuses: dict[str, list[str]] = {t.name: [] for t in github.TOOLS}
    refused: dict[str, str] = {}
    global REPO
    async with httpx.AsyncClient(event_hooks={"response": [record]}, timeout=30) as client:
        for repo in REPOS:
            REPO = repo
            for tool in github.TOOLS:
                seen.clear()
                try:
                    await tool.ainvoke(_args(tool, owner), client=client)
                except ToolValidationError as exc:
                    refused[tool.name] = str(exc)[:200]
                    continue
                except (APIError, CharterError):
                    pass
                if "accepted" in seen:
                    named[tool.name] |= {
                        x.strip() for x in seen["accepted"].split(",") if x.strip()
                    }
                    statuses[tool.name].append(seen["status"])

    rows, bad = [], 0
    for tool in github.TOOLS:
        if tool.name in refused:
            rows.append({"tool": tool.name, "probe": "refused locally", "note": refused[tool.name]})
            print(f"PROBE {tool.name:44} refused locally: {refused[tool.name][:120]}")
            continue
        accepted = named[tool.name]
        declared = [_options(r) for r in tool.scopes]
        offered = {o for options in declared for o in options}
        if not accepted:
            # GitHub checked no scope for this call in either context, so it confirms
            # nothing, except that a tool declaring none is right to.
            verdict = "agree" if not offered else "unconfirmed"
        elif offered and offered <= accepted:
            verdict = "agree"
        else:
            verdict = "disagree"
        bad += verdict == "disagree"
        rows.append(
            {
                "tool": tool.name,
                "statuses": statuses[tool.name],
                "accepted": sorted(accepted),
                "declared": [list(d) for d in declared],
                "verdict": verdict,
            }
        )
        mark = {"agree": "ok  ", "unconfirmed": "--  ", "disagree": "FAIL"}[verdict]
        print(
            f"{mark} {tool.name:44} {','.join(statuses[tool.name])}  GitHub accepts "
            f"{sorted(accepted) or '-'}  tool offers {sorted(offered) or '-'}"
        )
    counts = {
        v: sum(1 for r in rows if r.get("verdict") == v)
        for v in ("agree", "unconfirmed", "disagree")
    }
    print(
        f"\n{counts['agree']} agree, {counts['disagree']} disagree, {counts['unconfirmed']} where GitHub "
        f"named no scope, {sum(1 for r in rows if 'probe' in r)} not probed"
    )
    out = os.path.expanduser("~/.charter/live/github-scopes-check.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        json.dump(rows, f, indent=2)
    print(f"report: {out}")
    return 1 if bad else 0


# -----------------------------------------------------------------------------
# --kind fine_grained
# -----------------------------------------------------------------------------

NOT_SENT = {"notifications_mark_read", "notifications_mark_thread_read"}


def _accepted_sets(header: str) -> list[frozenset[str]]:
    """``a=read; b=read,c=write`` as the permission sets any one of which will do."""
    return [
        frozenset(p.strip() for p in alternative.split(",") if p.strip())
        for alternative in header.split(";")
        if alternative.strip()
    ]


def _with_reads(granted: set[str]) -> set[str]:
    """Write access to a permission includes read."""
    return granted | {g.replace("=write", "=read") for g in granted if g.endswith("=write")}


def _verdict(tool: Tool, header: str | None) -> tuple[str, str]:
    declared = tool.kind_scopes[github.FINE_GRAINED]
    if any(isinstance(r, Unavailable) for r in declared):
        return ("agree" if header is None else "disagree", "declared unavailable")
    if not header or header.startswith("allows_permissionless_access"):
        if not declared:
            return "agree", "no permission"
        return "unconfirmed", "GitHub named nothing"
    accepted = _accepted_sets(header)
    clauses = [_options(r) for r in declared]
    # Every way of meeting the declaration must meet one of GitHub's sets.
    for choice in itertools.product(*clauses):
        held = _with_reads(set(choice))
        if not any(s <= held for s in accepted):
            return "disagree", f"{sorted(choice)} meets none of {header!r}"
    return "agree", header


async def check_permissions(owner: str) -> int:
    token = os.environ.get("GITHUB_PERMISSION_PROBE_TOKEN", "")
    if not token.startswith("github_pat_"):
        sys.exit("GITHUB_PERMISSION_PROBE_TOKEN must be a fine-grained token (github_pat_...)")
    github.configure(StaticTokenProvider(token))
    seen: dict[str, Any] = {}

    async def record(response: httpx.Response) -> None:
        seen["accepted"] = response.headers.get("x-accepted-github-permissions")
        seen["status"] = response.status_code
        seen["method"] = response.request.method

    rows, bad = [], 0
    async with httpx.AsyncClient(event_hooks={"response": [record]}, timeout=30) as client:
        for tool in github.TOOLS:
            if tool.name in NOT_SENT:
                verdict, note = "agree", "not sent; GitHub documents no fine-grained access"
                rows.append({"tool": tool.name, "verdict": verdict, "note": note})
                print(f"ok   {tool.name:44} {note}")
                continue
            seen.clear()
            try:
                await tool.ainvoke(_args(tool, owner), client=client)
            except ToolValidationError as exc:
                rows.append({"tool": tool.name, "probe": "refused locally", "note": str(exc)[:200]})
                print(f"PROBE {tool.name:44} refused locally: {str(exc)[:120]}")
                continue
            except (APIError, CharterError):
                pass
            if seen.get("method") not in (None, "GET") and seen.get("status", 500) < 400:
                sys.exit(f"stopping: {tool.name} sent a {seen['method']} that succeeded")
            verdict, note = _verdict(tool, seen.get("accepted"))
            bad += verdict == "disagree"
            rows.append(
                {
                    "tool": tool.name,
                    "status": seen.get("status"),
                    "accepted": seen.get("accepted"),
                    "declared": [list(_options(r)) for r in tool.kind_scopes[github.FINE_GRAINED]],
                    "verdict": verdict,
                }
            )
            mark = {"agree": "ok  ", "unconfirmed": "--  ", "disagree": "FAIL"}[verdict]
            print(f"{mark} {tool.name:44} {seen.get('status')}  {note}")
    counts = {
        v: sum(1 for r in rows if r.get("verdict") == v)
        for v in ("agree", "unconfirmed", "disagree")
    }
    print(
        f"\n{counts['agree']} agree, {counts['disagree']} disagree, {counts['unconfirmed']} where "
        f"GitHub named nothing, {sum(1 for r in rows if 'probe' in r)} not probed"
    )
    out = os.path.expanduser("~/.charter/live/github-permissions-check.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        json.dump(rows, f, indent=2)
    print(f"report: {out}")
    return 1 if bad else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--owner", required=True, help="the account that owns harness-sandbox")
    ap.add_argument("--kind", choices=("oauth", "fine_grained"), default="oauth")
    cli = ap.parse_args()
    run = check_permissions if cli.kind == "fine_grained" else main
    sys.exit(asyncio.run(run(cli.owner)))
