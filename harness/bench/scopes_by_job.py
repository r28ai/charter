"""The Google scopes five common jobs ask for, per option, and whether any is restricted.

A restricted scope means Google's yearly security assessment (CASA) before anyone
outside the test-user list can connect. Charter's column is computed with
``scopes_for`` from the tools the job needs. The MCP server's columns are
transcribed from its source at a pinned release, because they are fixed
configuration rather than something a call reveals.

    cd harness && .venv/bin/python bench/scopes_by_job.py

No network. Prints a markdown table and writes ``results/bench/scopes_by_job.json``.
"""

from __future__ import annotations

import json
from pathlib import Path

from charter.auth import scopes_for
from charter.packs import gdocs, gdrive, gmail

OUT = Path(__file__).resolve().parent.parent / "results" / "bench" / "scopes_by_job.json"
A = "https://www.googleapis.com/auth/"

# Google's restricted category: developers.google.com/workspace/gmail/api/auth/scopes
# and developers.google.com/workspace/drive/api/guides/api-specific-auth, 2026-10-23.
RESTRICTED = {
    "https://mail.google.com/",
    *(
        A + s
        for s in (
            "gmail.readonly",
            "gmail.compose",
            "gmail.modify",
            "gmail.metadata",
            "gmail.insert",
            "gmail.settings.basic",
            "gmail.settings.sharing",
            "drive",
            "drive.readonly",
            "drive.metadata",
            "drive.metadata.readonly",
            "drive.activity",
            "drive.activity.readonly",
            "drive.meet.readonly",
            "drive.scripts",
        )
    ),
}

JOBS = {
    "send notification emails": [gmail.messages_send],
    "draft replies for a person to send": [
        gmail.threads_list,
        gmail.threads_get,
        gmail.drafts_create,
    ],
    "triage the inbox with labels": [
        gmail.threads_list,
        gmail.threads_get,
        gmail.threads_modify,
        gmail.labels_list,
        gmail.labels_create,
    ],
    "write a report into a new Google Doc": [gdocs.documents_create, gdocs.documents_batch_update],
    "answer questions from Drive files": [gdrive.files_list, gdrive.files_export],
}

# taylorwilsdon/google_workspace_mcp v2.1.2 (2026-10-21), the most-starred Gmail
# MCP server on GitHub on 2026-10-23 (3,404 stars). auth/scopes.py and
# auth/permissions.py. Every configuration also asks for openid, userinfo.email
# and userinfo.profile, which are non-sensitive and left out here.
_GMAIL_ALL = [
    "gmail.readonly",
    "gmail.send",
    "gmail.compose",
    "gmail.modify",
    "gmail.labels",
    "gmail.settings.basic",
]
_DRIVE_ALL = ["drive", "drive.readonly", "drive.file"]
_DOCS_ALL = ["documents.readonly", "documents", "drive.readonly", "drive.file"]
# --permissions levels are cumulative: each includes every level before it.
_GMAIL_LEVELS = {
    "readonly": ["gmail.readonly"],
    "organize": ["gmail.readonly", "gmail.labels", "gmail.modify"],
    "drafts": ["gmail.readonly", "gmail.labels", "gmail.modify", "gmail.compose"],
    "send": ["gmail.readonly", "gmail.labels", "gmail.modify", "gmail.compose", "gmail.send"],
}
WORKSPACE_MCP = {
    # (`--tools <service>`, narrowest `--permissions` that can do the job)
    "send notification emails": (_GMAIL_ALL, ("gmail:send", _GMAIL_LEVELS["send"])),
    "draft replies for a person to send": (_GMAIL_ALL, ("gmail:drafts", _GMAIL_LEVELS["drafts"])),
    "triage the inbox with labels": (_GMAIL_ALL, ("gmail:organize", _GMAIL_LEVELS["organize"])),
    "write a report into a new Google Doc": (
        _DOCS_ALL,
        ("docs:full", ["documents", "drive.readonly", "drive.file"]),
    ),
    "answer questions from Drive files": (_DRIVE_ALL, ("drive:readonly", ["drive.readonly"])),
}


def _short(s: str) -> str:
    return s.removeprefix(A)


def _restricted(scopes) -> bool:
    return any((s if s.startswith("https://") else A + s) in RESTRICTED for s in scopes)


def main() -> None:
    rows = []
    for job, tools in JOBS.items():
        charter = scopes_for(tools)
        per_service, (level, narrowest) = WORKSPACE_MCP[job]
        rows.append(
            {
                "job": job,
                "charter": [_short(s) for s in charter],
                "charter_restricted": _restricted(charter),
                "workspace_mcp_service": per_service,
                "workspace_mcp_service_restricted": _restricted(per_service),
                "workspace_mcp_narrowest_flag": level,
                "workspace_mcp_narrowest": narrowest,
                "workspace_mcp_narrowest_restricted": _restricted(narrowest),
            }
        )
    yes = lambda b: "**yes**" if b else "no"  # noqa: E731
    print(
        "| job | Charter asks for | CASA | workspace-mcp `--tools` | CASA | narrowest `--permissions` | CASA |"
    )
    print("|---|---|---|---|---|---|---|")
    for r in rows:
        print(
            f"| {r['job']} | {', '.join(r['charter'])} | {yes(r['charter_restricted'])} | "
            f"{', '.join(r['workspace_mcp_service'])} | {yes(r['workspace_mcp_service_restricted'])} | "
            f"`{r['workspace_mcp_narrowest_flag']}`: {', '.join(r['workspace_mcp_narrowest'])} | "
            f"{yes(r['workspace_mcp_narrowest_restricted'])} |"
        )
    n = len(rows)
    print()
    print(
        f"jobs needing CASA: Charter {sum(r['charter_restricted'] for r in rows)}/{n}, "
        f"workspace-mcp --tools {sum(r['workspace_mcp_service_restricted'] for r in rows)}/{n}, "
        f"narrowest --permissions {sum(r['workspace_mcp_narrowest_restricted'] for r in rows)}/{n}"
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows, indent=2) + "\n")


if __name__ == "__main__":
    main()
