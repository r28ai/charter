"""
Delete harness fixtures a run left behind.

Every scenario namespaces its fixtures with a tag from
:func:`~charter_harness.context.mint_namespace` - ``h`` plus six hex characters -
and teardown removes them. Teardown does not run when a campaign is killed, so a
hung run leaves labels, sheets, documents and issues in live accounts. They are
not inert: a stale ``[h73c586] URGENT:`` issue is a distractor the next run's
judge can see.

    .venv/bin/python scripts/clean_orphans.py            # scan, delete nothing
    .venv/bin/python scripts/clean_orphans.py --delete
    .venv/bin/python scripts/clean_orphans.py --delete --ns h73c586,h939c81

Only names matching the namespace pattern are ever touched, so a real label or
document in the same account is invisible to this script. GitHub issues cannot
be deleted through the REST API and are closed instead.
"""

from __future__ import annotations

import argparse
import asyncio
import re

from charter_harness.settings import load, wire_packs
from charter_harness.world import World

NS = re.compile(r"\bh[0-9a-f]{6}\b")

# Gmail's own labels are never candidates, whatever they are called.
SYSTEM_LABELS = {
    "INBOX",
    "SENT",
    "DRAFT",
    "SPAM",
    "TRASH",
    "UNREAD",
    "STARRED",
    "IMPORTANT",
    "CHAT",
}


def wanted(text: str, only: set[str]) -> bool:
    found = NS.findall(text or "")
    return bool(found) and (not only or bool(set(found) & only))


async def gmail(w: World, only: set[str], delete: bool) -> list[str]:
    done = []
    labels = await w.gmail.http.json("GET", "gmail/v1/users/me/labels")
    for label in labels.get("labels", []):
        if label.get("type") == "system" or label["id"] in SYSTEM_LABELS:
            continue
        if not wanted(label.get("name", ""), only):
            continue
        done.append(f"label {label['name']}")
        if delete:
            await w.gmail.http.request("DELETE", f"gmail/v1/users/me/labels/{label['id']}")

    # Seeded mail carries the namespace in the subject.
    for ns in sorted(only) or [""]:
        query = f"subject:{ns}" if ns else "subject:h"
        found = await w.gmail.http.json(
            "GET", "gmail/v1/users/me/threads", params={"q": query, "maxResults": 100}
        )
        for thread in found.get("threads") or []:
            detail = await w.gmail.http.json("GET", f"gmail/v1/users/me/threads/{thread['id']}")
            subject = ""
            for header in detail["messages"][0].get("payload", {}).get("headers", []):
                if header["name"].lower() == "subject":
                    subject = header["value"]
            if not wanted(subject, only):
                continue
            done.append(f"thread {subject[:50]}")
            if delete:
                await w.gmail.http.request("DELETE", f"gmail/v1/users/me/threads/{thread['id']}")
    return done


async def drive(w: World, only: set[str], delete: bool) -> list[str]:
    done = []
    for item in await w.drive.files_list(name_contains="h"):
        if not wanted(item.get("name", ""), only):
            continue
        done.append(f"file {item['name'][:50]}")
        if delete:
            await w.drive.file_delete(item["id"])
    return done


async def linear(w: World, only: set[str], delete: bool) -> list[str]:
    done = []
    team = await w.linear.team_id()
    query = "query($t:String!){team(id:$t){issues(first:250){nodes{id identifier title}}}}"
    nodes = (await w.linear.gql(query, {"t": team}))["team"]["issues"]["nodes"]
    for node in nodes:
        if not wanted(node.get("title", ""), only):
            continue
        done.append(f"issue {node['identifier']} {node['title'][:40]}")
        if delete:
            await w.linear.gql(
                "mutation($id:String!){issueDelete(id:$id){success}}", {"id": node["id"]}
            )
    return done


async def github(w: World, only: set[str], delete: bool) -> list[str]:
    done = []
    repo = await w.github.ensure_sandbox()
    owner, name = repo["full_name"].split("/", 1)
    issues = await w.github.http.json(
        "GET", f"repos/{owner}/{name}/issues", params={"state": "open", "per_page": 100}
    )
    for issue in issues:
        if "pull_request" in issue or not wanted(issue.get("title", ""), only):
            continue
        # REST cannot delete an issue; closing is the most teardown can do.
        done.append(f"issue #{issue['number']} {issue['title'][:40]} (close)")
        if delete:
            await w.github.http.request(
                "PATCH", f"repos/{owner}/{name}/issues/{issue['number']}", json={"state": "closed"}
            )
    return done


async def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--delete", action="store_true", help="actually remove them (default: scan only)"
    )
    parser.add_argument("--ns", help="comma-separated namespaces; default every namespace found")
    args = parser.parse_args()
    only = {n.strip() for n in args.ns.split(",")} if args.ns else set()

    world = World(wire_packs(load()))
    total = 0
    try:
        for name, fn in (
            ("gmail", gmail),
            ("drive", drive),
            ("linear", linear),
            ("github", github),
        ):
            try:
                found = await fn(world, only, args.delete)
            except Exception as exc:  # noqa: BLE001 - one provider failing must not strand the rest
                print(f"{name:8} ERROR {str(exc).splitlines()[0][:100]}")
                continue
            verb = "deleted" if args.delete else "would delete"
            print(f"{name:8} {verb} {len(found)}")
            for line in found[:40]:
                print(f"         {line}")
            total += len(found)
    finally:
        await world.aclose()

    print(f"\n{total} fixture(s) {'removed' if args.delete else 'found'}.")
    if total and not args.delete:
        print("Re-run with --delete to remove them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
