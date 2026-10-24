#!/usr/bin/env python
"""Does each Google tool work with exactly the scope it declares, and fail without it?

Deliberately not a test, like ``live_google_check.py``: the suite is offline by
rule. The offline suite checks every declared scope against the scopes Google's
discovery documents list for the method. This asks Google itself.

Two commands::

    uv run python scripts/live_google_scopes_check.py connect
    uv run python scripts/live_google_scopes_check.py check --account you@example.com

``connect`` asks for one consent covering every scope the six Google packs
declare, and keeps the grant in ``$CHARTER_LIVE_DIR`` (default ``~/.charter/live``),
readable by you alone. Sign in with a test account: ``check`` creates and deletes
a label, a draft, a folder, a document, a spreadsheet, a form and three calendar
events in it.

``check`` first confirms that Google narrows a token when a refresh asks for fewer
scopes than the grant holds; everything after depends on it. Then, for every tool,
it mints a token holding only the tool's declared scopes and calls the tool, and
mints one holding only ``userinfo.email`` and calls it again. The first must get
past Google's scope check and the second must not:

- **accepted**: 2xx, or any refusal about the request itself (400, 404, 409). The
  probes aim writes at ids that do not exist, so they fail after the scope check
  and change nothing.
- **insufficient**: 403 saying the token's scopes are insufficient.

Three tools are never called through Charter. ``messages_send`` would send mail
with any valid arguments, so its method is probed directly with an empty body,
which Gmail must refuse. ``drafts_send`` is called only with a draft id that does
not exist. ``files_empty_trash`` empties the account's trash and is not probed.

Reads ``GOOGLE_CLIENT_ID``, ``GOOGLE_CLIENT_SECRET`` and ``GOOGLE_REDIRECT_URI`` from
the environment or the repo's ``.env``; the redirect must be a localhost URL the
client has registered. Nothing prints a token.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path as FsPath
from typing import Any, Callable, Optional
from urllib.parse import parse_qs, urlparse

import httpx

from charter import APIError, CharterError, InsufficientScope, Tool, ToolValidationError
from charter.auth import OAuth2Flow, OAuth2Server, StaticTokenProvider, states_match

ROOT = FsPath(__file__).resolve().parent.parent
LIVE = FsPath(os.environ.get("CHARTER_LIVE_DIR", FsPath.home() / ".charter/live"))
GRANT = LIVE / "google-scopes.json"
REPORT = LIVE / "google-scopes-check.json"
PACKS = ("gmail", "gdrive", "gcalendar", "gdocs", "gsheets", "gforms")
EMAIL_ONLY = "https://www.googleapis.com/auth/userinfo.email"
IDENTITY = ["openid", EMAIL_ONLY]
TOKEN_URL = "https://oauth2.googleapis.com/token"

GOOGLE = OAuth2Server(
    issuer="https://accounts.google.com",
    authorization_endpoint="https://accounts.google.com/o/oauth2/v2/auth",
    token_endpoint=TOKEN_URL,
    token_endpoint_auth_method="client_secret_post",
    authorization_params={"access_type": "offline", "prompt": "consent"},
)

# Ids no account has. A write aimed at one is refused after the scope check.
NO_GMAIL = "18c0ffee00000000"
NO_DRIVE = "1charterScopeProbeNoSuchFile000000000000"
NO_EVENT = "charterprobe0000000000"
NO_SHEET = "1charterScopeProbeNoSuchSheet0000000000000"


def _env(name: str) -> str:
    if os.environ.get(name):
        return os.environ[name]
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            key, _, value = line.partition("=")
            if key.strip() == name:
                return value.strip().strip("'\"")
    sys.exit(f"{name} is not set (environment or {env})")


def _tools() -> list[tuple[str, Tool]]:
    out = []
    for pack in PACKS:
        module = importlib.import_module(f"charter.packs.{pack}")
        out.extend((pack, tool) for tool in module.TOOLS)
    return out


def _options(requirement) -> tuple[str, ...]:
    return getattr(requirement, "options", (requirement,))


def declared_scopes() -> list[str]:
    return sorted({o for _, t in _tools() for r in t.scopes for o in _options(r)})


def _token_sets(tool: Tool) -> list[tuple[str, ...]]:
    """One scope set per option a tool offers: that option, plus the narrowest of
    each other requirement. Every option must work on its own."""
    sets = []
    for i, requirement in enumerate(tool.scopes):
        for option in _options(requirement):
            others = [_options(r)[0] for j, r in enumerate(tool.scopes) if j != i]
            sets.append(tuple(sorted({option, *others})))
    return sets


# -----------------------------------------------------------------------------
# connect
# -----------------------------------------------------------------------------


def _wait_for_callback(host: str, port: int) -> dict[str, str]:
    captured: dict[str, str] = {}

    class Callback(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - http.server API
            captured.update({k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()})
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Connected. You can close this tab and go back to the terminal.")

        def log_message(self, *_):
            pass

    with HTTPServer((host, port), Callback) as server:
        server.handle_request()
    return captured


async def connect() -> int:
    redirect_uri = _env("GOOGLE_REDIRECT_URI")
    redirect = urlparse(redirect_uri)
    if redirect.hostname not in ("localhost", "127.0.0.1") or not redirect.port:
        sys.exit(f"GOOGLE_REDIRECT_URI must be a localhost URL with a port, got {redirect_uri}")
    client_id, secret = _env("GOOGLE_CLIENT_ID"), _env("GOOGLE_CLIENT_SECRET")
    flow = OAuth2Flow(GOOGLE, client_id=client_id, client_secret=secret, redirect_uri=redirect_uri)
    scopes = IDENTITY + declared_scopes()
    request = flow.authorize(scopes)
    print(f"Asking for {len(scopes)} scopes. Open this and sign in with the TEST account:\n")
    print(request.url)
    print(f"\nWaiting on {redirect_uri} ...")
    params = _wait_for_callback(redirect.hostname or "localhost", redirect.port)
    if "error" in params:
        sys.exit(f"Google returned {params['error']}")
    if not states_match(request.state, params.get("state", "")):
        sys.exit("state mismatch; start over")
    grant = await flow.exchange(params["code"], code_verifier=request.code_verifier)
    if not grant.refresh_token:
        sys.exit(
            "no refresh token came back; remove the app at myaccount.google.com/permissions and retry"
        )
    missing = sorted(set(scopes) - set(grant.scopes))
    if missing:
        print(f"Not granted (a box left unticked on the consent screen): {missing}")
    async with httpx.AsyncClient() as http:
        token = await _mint(http, client_id, secret, grant.refresh_token, IDENTITY)
        email = (
            await http.get(
                "https://openidconnect.googleapis.com/v1/userinfo",
                headers={"Authorization": f"Bearer {token}"},
            )
        ).json()["email"]
    LIVE.mkdir(parents=True, exist_ok=True)
    GRANT.write_text(
        json.dumps(
            {
                "refresh_token": grant.refresh_token,
                "client_id": client_id,
                "email": email,
                "scopes": sorted(grant.scopes),
                "connected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
        )
    )
    GRANT.chmod(0o600)
    print(f"Connected {email}, {len(grant.scopes)} scopes, grant kept in {GRANT}")
    return 0


# -----------------------------------------------------------------------------
# check
# -----------------------------------------------------------------------------


async def _mint(http: httpx.AsyncClient, client_id: str, secret: str, refresh: str, scopes) -> str:
    """An access token holding only ``scopes``, from a grant that holds more."""
    r = await http.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh,
            "client_id": client_id,
            "client_secret": secret,
            "scope": " ".join(scopes),
        },
    )
    if r.status_code != 200:
        raise SystemExit(
            f"token endpoint refused a narrowed refresh: {r.status_code} {r.text[:300]}"
        )
    return r.json()["access_token"]


async def _token_scopes(http: httpx.AsyncClient, token: str) -> set[str]:
    r = await http.get("https://oauth2.googleapis.com/tokeninfo", params={"access_token": token})
    return set(r.json().get("scope", "").split())


def _configure(token: str) -> None:
    for pack in PACKS:
        importlib.import_module(f"charter.packs.{pack}").configure(StaticTokenProvider(token))


def _classify(status: int, body: str) -> str:
    """accepted, insufficient, or unreached: a refusal that is not about the request.

    A 403 is not one thing. "Insufficient authentication scopes" is the answer
    this check is after; "has not been used in project ... or it is disabled" means
    the API is off in the Cloud project and the scope check never ran, so it proves
    nothing either way. Counting that as accepted is how the first run reported six
    Forms tools as passing when none had been reached.
    """
    text = body.lower()
    if status == 403 and (
        "insufficient authentication scopes" in text
        or "access_token_scope_insufficient" in text
        or "insufficientpermissions" in text
    ):
        return "insufficient"
    if status == 401 or (
        status == 403
        and (
            "service_disabled" in text
            or "has not been used in project" in text
            or "it is disabled" in text
        )
    ):
        return "unreached"
    return "accepted"


class Ctx:
    """What the probes need from the account, read once with the full grant."""

    def __init__(self, email: str, stamp: str) -> None:
        self.email = email
        self.stamp = stamp
        self.message_id = NO_GMAIL
        self.thread_id = NO_GMAIL
        self.file_id = NO_DRIVE
        self.cleanup: list[tuple[str, str]] = []  # (kind, id), removed with the full grant


def _event(ctx: Ctx, **extra: Any) -> dict[str, Any]:
    return {
        "summary": f"[charter scope probe {ctx.stamp}]",
        "start": {"date_time": "2031-01-02T03:00:00Z"},
        "end": {"date_time": "2031-01-02T03:15:00Z"},
        **extra,
    }


# Arguments per tool. A tool missing here is a probe nobody wrote, and the check
# says so rather than guessing. Each value is (args, what the call creates, if anything).
Probe = Callable[[Ctx], tuple[dict[str, Any], Optional[str]]]
ME = {"userId": "me"}
PROBES: dict[str, Probe] = {
    # gmail
    "gmail.messages_list": lambda c: ({**ME, "maxResults": 1}, None),
    "gmail.messages_get": lambda c: ({**ME, "id": c.message_id, "format": "minimal"}, None),
    "gmail.messages_attachments_get": lambda c: (
        {**ME, "messageId": c.message_id, "id": "nosuchattachment"},
        None,
    ),
    "gmail.messages_modify": lambda c: (
        {**ME, "id": NO_GMAIL, "body": {"addLabelIds": ["STARRED"]}},
        None,
    ),
    "gmail.messages_batch_modify": lambda c: (
        {**ME, "body": {"ids": [NO_GMAIL], "addLabelIds": ["STARRED"]}},
        None,
    ),
    "gmail.threads_list": lambda c: ({**ME, "maxResults": 1}, None),
    "gmail.threads_get": lambda c: ({**ME, "id": c.thread_id, "format": "minimal"}, None),
    "gmail.threads_modify": lambda c: (
        {**ME, "id": NO_GMAIL, "body": {"addLabelIds": ["STARRED"]}},
        None,
    ),
    "gmail.threads_trash": lambda c: ({**ME, "id": NO_GMAIL}, None),
    "gmail.threads_untrash": lambda c: ({**ME, "id": NO_GMAIL}, None),
    "gmail.threads_delete": lambda c: ({**ME, "id": NO_GMAIL}, None),
    "gmail.drafts_create": lambda c: (
        {
            **ME,
            "body": {
                "message": {
                    "raw": {
                        "to": c.email,
                        "subject": f"[charter scope probe {c.stamp}]",
                        "body": "A draft. Never sent.",
                    }
                }
            },
        },
        "gmail.draft",
    ),
    "gmail.drafts_get": lambda c: ({**ME, "id": "r0000000000000000000"}, None),
    "gmail.drafts_list": lambda c: ({**ME, "maxResults": 1}, None),
    "gmail.drafts_update": lambda c: (
        {
            **ME,
            "id": "r0000000000000000000",
            "body": {"message": {"raw": {"to": c.email, "subject": "x", "body": "x"}}},
        },
        None,
    ),
    "gmail.drafts_delete": lambda c: ({**ME, "id": "r0000000000000000000"}, None),
    "gmail.drafts_send": lambda c: ({**ME, "body": {"id": "r0000000000000000000"}}, None),
    "gmail.labels_list": lambda c: (ME, None),
    "gmail.labels_get": lambda c: ({**ME, "id": "INBOX"}, None),
    "gmail.labels_create": lambda c: (
        {**ME, "body": {"name": f"charter-scope-probe-{c.stamp}"}},
        "gmail.label",
    ),
    "gmail.labels_update": lambda c: (
        {**ME, "id": "Label_0000000000", "body": {"name": "x"}},
        None,
    ),
    "gmail.labels_patch": lambda c: ({**ME, "id": "Label_0000000000", "body": {"name": "x"}}, None),
    "gmail.labels_delete": lambda c: ({**ME, "id": "Label_0000000000"}, None),
    # drive
    "gdrive.files_list": lambda c: ({"page_size": 1}, None),
    "gdrive.files_get": lambda c: ({"file_id": c.file_id}, None),
    "gdrive.files_export": lambda c: ({"file_id": NO_DRIVE, "mime_type": "text/plain"}, None),
    "gdrive.files_create": lambda c: (
        {
            "file": {
                "name": f"charter-scope-probe-{c.stamp}",
                "mime_type": "application/vnd.google-apps.folder",
            }
        },
        "drive.file",
    ),
    "gdrive.files_update": lambda c: ({"file_id": NO_DRIVE, "file": {"description": "x"}}, None),
    "gdrive.files_copy": lambda c: ({"file_id": NO_DRIVE, "file": {"name": "x"}}, None),
    "gdrive.files_delete": lambda c: ({"file_id": NO_DRIVE}, None),
    "gdrive.permissions_create": lambda c: (
        {
            "file_id": NO_DRIVE,
            "permission": {"type": "anyone", "role": "reader"},
            "send_notification_email": False,
        },
        None,
    ),
    "gdrive.permissions_list": lambda c: ({"file_id": c.file_id}, None),
    "gdrive.permissions_get": lambda c: ({"file_id": NO_DRIVE, "permission_id": "anyone"}, None),
    "gdrive.permissions_update": lambda c: (
        {"file_id": NO_DRIVE, "permission_id": "anyone", "permission": {"role": "reader"}},
        None,
    ),
    "gdrive.permissions_delete": lambda c: ({"file_id": NO_DRIVE, "permission_id": "anyone"}, None),
    "gdrive.comments_list": lambda c: ({"file_id": c.file_id, "fields": "comments(id)"}, None),
    "gdrive.comments_create": lambda c: (
        {"file_id": NO_DRIVE, "comment": {"content": "x"}, "fields": "id"},
        None,
    ),
    "gdrive.comments_update": lambda c: (
        {"file_id": NO_DRIVE, "comment_id": "x", "comment": {"content": "x"}, "fields": "id"},
        None,
    ),
    "gdrive.comments_delete": lambda c: ({"file_id": NO_DRIVE, "comment_id": "x"}, None),
    "gdrive.replies_create": lambda c: (
        {"file_id": NO_DRIVE, "comment_id": "x", "reply": {"content": "x"}},
        None,
    ),
    "gdrive.replies_update": lambda c: (
        {"file_id": NO_DRIVE, "comment_id": "x", "reply_id": "x", "reply": {"content": "x"}},
        None,
    ),
    "gdrive.replies_delete": lambda c: (
        {"file_id": NO_DRIVE, "comment_id": "x", "reply_id": "x"},
        None,
    ),
    "gdrive.revisions_list": lambda c: ({"file_id": c.file_id}, None),
    "gdrive.revisions_get": lambda c: ({"file_id": NO_DRIVE, "revision_id": "x"}, None),
    "gdrive.drives_list": lambda c: ({"page_size": 1}, None),
    "gdrive.drives_get": lambda c: ({"drive_id": "0AcharterNoSuchDrive"}, None),
    "gdrive.about_get": lambda c: ({"fields": "user,storageQuota"}, None),
    # calendar
    "gcalendar.events_list": lambda c: ({"calendar_id": "primary", "max_results": 1}, None),
    "gcalendar.events_get": lambda c: ({"calendar_id": "primary", "event_id": NO_EVENT}, None),
    "gcalendar.events_instances": lambda c: (
        {"calendar_id": "primary", "event_id": NO_EVENT},
        None,
    ),
    "gcalendar.events_insert": lambda c: (
        {"calendar_id": "primary", "send_updates": "none", "event": _event(c)},
        "calendar.event",
    ),
    "gcalendar.events_update": lambda c: (
        {"calendar_id": "primary", "event_id": NO_EVENT, "event": _event(c)},
        None,
    ),
    "gcalendar.events_patch": lambda c: (
        {"calendar_id": "primary", "event_id": NO_EVENT, "event": {"summary": "x"}},
        None,
    ),
    "gcalendar.events_move": lambda c: (
        {"calendar_id": "primary", "event_id": NO_EVENT, "destination": "primary"},
        None,
    ),
    "gcalendar.events_quick_add": lambda c: (
        {
            "calendar_id": "primary",
            "send_updates": "none",
            "text": f"charter scope probe {c.stamp} on 3 January 2031 at 3am",
        },
        "calendar.event",
    ),
    "gcalendar.events_import": lambda c: (
        {
            "calendar_id": "primary",
            "event": _event(c, i_cal_uid=f"charter-scope-probe-{c.stamp}@r28.ai"),
        },
        "calendar.event",
    ),
    "gcalendar.events_delete": lambda c: (
        {"calendar_id": "primary", "event_id": NO_EVENT, "send_updates": "none"},
        None,
    ),
    "gcalendar.calendar_list_list": lambda c: ({"max_results": 1}, None),
    "gcalendar.calendar_list_get": lambda c: ({"calendar_id": "primary"}, None),
    "gcalendar.calendars_get": lambda c: ({"calendar_id": "primary"}, None),
    # docs
    "gdocs.documents_get": lambda c: ({"document_id": NO_SHEET}, None),
    "gdocs.documents_create": lambda c: (
        {"body": {"title": f"charter scope probe {c.stamp}"}},
        "drive.file",
    ),
    "gdocs.documents_batch_update": lambda c: (
        {
            "document_id": NO_SHEET,
            "body": {"requests": [{"insert_text": {"text": "x", "end_of_segment_location": {}}}]},
        },
        None,
    ),
    # sheets
    "gsheets.spreadsheets_values_get": lambda c: (
        {"spreadsheet_id": NO_SHEET, "range": "A1"},
        None,
    ),
    "gsheets.spreadsheets_values_update": lambda c: (
        {
            "spreadsheet_id": NO_SHEET,
            "range": "A1",
            "value_input_option": "RAW",
            "value_range": {"values": [["x"]]},
        },
        None,
    ),
    "gsheets.spreadsheets_values_append": lambda c: (
        {
            "spreadsheet_id": NO_SHEET,
            "range": "A1",
            "value_input_option": "RAW",
            "value_range": {"values": [["x"]]},
        },
        None,
    ),
    "gsheets.spreadsheets_values_clear": lambda c: (
        {"spreadsheet_id": NO_SHEET, "range": "A1"},
        None,
    ),
    "gsheets.spreadsheets_values_batch_get": lambda c: (
        {"spreadsheet_id": NO_SHEET, "ranges": ["A1"]},
        None,
    ),
    "gsheets.spreadsheets_values_batch_update": lambda c: (
        {
            "spreadsheet_id": NO_SHEET,
            "value_input_option": "RAW",
            "data": [{"range": "A1", "values": [["x"]]}],
        },
        None,
    ),
    "gsheets.spreadsheets_values_batch_clear": lambda c: (
        {"spreadsheet_id": NO_SHEET, "ranges": ["A1"]},
        None,
    ),
    "gsheets.values_batch_get_by_data_filter": lambda c: (
        {"spreadsheet_id": NO_SHEET, "data_filters": [{"a1_range": "A1"}]},
        None,
    ),
    "gsheets.values_batch_update_by_data_filter": lambda c: (
        {
            "spreadsheet_id": NO_SHEET,
            "value_input_option": "RAW",
            "data": [{"data_filter": {"a1_range": "A1"}, "values": [["x"]]}],
        },
        None,
    ),
    "gsheets.values_batch_clear_by_data_filter": lambda c: (
        {"spreadsheet_id": NO_SHEET, "data_filters": [{"a1_range": "A1"}]},
        None,
    ),
    "gsheets.spreadsheets_create": lambda c: (
        {"spreadsheet": {"properties": {"title": f"charter scope probe {c.stamp}"}}},
        "drive.file",
    ),
    "gsheets.spreadsheets_get": lambda c: ({"spreadsheet_id": NO_SHEET}, None),
    "gsheets.spreadsheets_batch_update": lambda c: (
        {
            "spreadsheet_id": NO_SHEET,
            "requests": [
                {"update_spreadsheet_properties": {"properties": {"title": "x"}, "fields": "title"}}
            ],
        },
        None,
    ),
    "gsheets.spreadsheets_sheets_copy_to": lambda c: (
        {
            "spreadsheet_id": NO_SHEET,
            "sheet_id": 0,
            "body": {"destination_spreadsheet_id": NO_SHEET},
        },
        None,
    ),
    "gsheets.spreadsheets_get_by_data_filter": lambda c: ({"spreadsheet_id": NO_SHEET}, None),
    "gsheets.spreadsheets_developer_metadata_get": lambda c: (
        {"spreadsheet_id": NO_SHEET, "metadata_id": 1},
        None,
    ),
    "gsheets.spreadsheets_developer_metadata_search": lambda c: (
        {"spreadsheet_id": NO_SHEET, "data_filters": [{"a1_range": "A1"}]},
        None,
    ),
    # forms
    "gforms.forms_create": lambda c: (
        {"unpublished": True, "body": {"info": {"title": f"charter scope probe {c.stamp}"}}},
        "drive.file",
    ),
    "gforms.forms_get": lambda c: ({"form_id": NO_SHEET}, None),
    "gforms.forms_batch_update": lambda c: (
        {
            "form_id": NO_SHEET,
            "body": {
                "requests": [
                    {
                        "update_form_info": {
                            "info": {"description": "x"},
                            "update_mask": "description",
                        }
                    }
                ]
            },
        },
        None,
    ),
    "gforms.forms_set_publish_settings": lambda c: (
        {
            "form_id": NO_SHEET,
            "body": {
                "publish_settings": {
                    "publish_state": {"is_published": False, "is_accepting_responses": False}
                }
            },
        },
        None,
    ),
    "gforms.forms_responses_get": lambda c: ({"form_id": NO_SHEET, "response_id": "x"}, None),
    "gforms.forms_responses_list": lambda c: ({"form_id": NO_SHEET}, None),
}
NOT_PROBED = {"gdrive.files_empty_trash": "empties the account's trash; irreversible"}
DIRECT = {
    "gmail.messages_send": ("POST", "https://gmail.googleapis.com/gmail/v1/users/me/messages/send")
}


def _created_id(kind: str, result: Any) -> Optional[str]:
    if not isinstance(result, dict):
        return None
    for key in ("id", "documentId", "spreadsheetId", "formId"):
        if result.get(key):
            return str(result[key])
    return None


async def _call(
    http: httpx.AsyncClient, name: str, tool: Tool, ctx: Ctx, token: str
) -> dict[str, Any]:
    """One call, classified. Creates are recorded for cleanup."""
    if name in DIRECT:
        method, url = DIRECT[name]
        r = await http.request(method, url, headers={"Authorization": f"Bearer {token}"}, json={})
        return {
            "status": r.status_code,
            "outcome": _classify(r.status_code, r.text),
            "note": "probed directly with an empty body; through the tool it would send mail",
        }
    args, creates = PROBES[name](ctx)
    _configure(token)
    try:
        result = await tool.ainvoke(args)
    except ToolValidationError as exc:
        return {"status": None, "outcome": "probe-error", "note": str(exc)[:300]}
    except InsufficientScope as exc:
        # Google's standard challenge, read by the runtime itself.
        return {"status": exc.status_code, "outcome": "insufficient", "note": str(exc)[:160]}
    except APIError as exc:
        return {
            "status": exc.status_code,
            "outcome": _classify(exc.status_code, exc.body),
            "note": exc.body[:160],
        }
    except CharterError as exc:
        return {
            "status": None,
            "outcome": "probe-error",
            "note": f"{type(exc).__name__}: {str(exc)[:300]}",
        }
    if creates:
        created = _created_id(creates, result)
        if created:
            ctx.cleanup.append((creates, created))
    return {"status": 200, "outcome": "accepted", "note": ""}


async def _cleanup(http: httpx.AsyncClient, token: str, ctx: Ctx) -> list[str]:
    headers = {"Authorization": f"Bearer {token}"}
    urls = {
        "gmail.draft": "https://gmail.googleapis.com/gmail/v1/users/me/drafts/{}",
        "gmail.label": "https://gmail.googleapis.com/gmail/v1/users/me/labels/{}",
        "drive.file": "https://www.googleapis.com/drive/v3/files/{}",
        "calendar.event": "https://www.googleapis.com/calendar/v3/calendars/primary/events/{}?sendUpdates=none",
    }
    left = []
    for kind, ident in ctx.cleanup:
        r = await http.delete(urls[kind].format(ident), headers=headers)
        if r.status_code not in (200, 204, 404, 410):
            left.append(f"{kind} {ident}: {r.status_code}")
    return left


async def check(account: str, only: str = "") -> int:
    if not GRANT.exists():
        sys.exit(f"no grant at {GRANT}; run `connect` first")
    grant = json.loads(GRANT.read_text())
    if grant["email"].lower() != account.lower():
        sys.exit(f"the stored grant is for {grant['email']}, not {account}; refusing to touch it")
    client_id, secret, refresh = (
        grant["client_id"],
        _env("GOOGLE_CLIENT_SECRET"),
        grant["refresh_token"],
    )
    granted = set(grant["scopes"])
    ctx = Ctx(grant["email"], time.strftime("%Y%m%d%H%M%S"))
    rows: list[dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=60) as http:
        # 1. Does Google narrow a token on refresh? Everything below depends on it.
        labels = "https://www.googleapis.com/auth/gmail.labels"
        narrow = await _mint(http, client_id, secret, refresh, [labels])
        held = await _token_scopes(http, narrow)
        r = await http.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages?maxResults=1",
            headers={"Authorization": f"Bearer {narrow}"},
        )
        narrows = held == {labels} and r.status_code == 403
        print(
            f"narrowed refresh: token holds {sorted(held)}; messages.list with it -> {r.status_code}"
        )
        if not narrows:
            sys.exit("Google did not narrow the token, so a per-tool check cannot be made this way")

        # 2. Read what the probes need, with the full grant.
        full = await _mint(http, client_id, secret, refresh, sorted(granted))
        h = {"Authorization": f"Bearer {full}"}
        msgs = (
            await http.get(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages?maxResults=1", headers=h
            )
        ).json().get("messages") or []
        if msgs:
            ctx.message_id, ctx.thread_id = msgs[0]["id"], msgs[0]["threadId"]
        files = (
            await http.get(
                "https://www.googleapis.com/drive/v3/files",
                headers=h,
                params={
                    "pageSize": 1,
                    "q": "'me' in owners and trashed = false and mimeType != 'application/vnd.google-apps.folder'",
                },
            )
        ).json().get("files") or []
        if files:
            ctx.file_id = files[0]["id"]

        # 3. Every tool: its declared scopes, then none of them.
        none_token = await _mint(http, client_id, secret, refresh, [EMAIL_ONLY])
        tokens: dict[tuple[str, ...], str] = {}
        try:
            for pack, tool in _tools():
                name = f"{pack}.{tool.name}"
                if only and not any(name.startswith(prefix) for prefix in only.split(",")):
                    continue
                if name in NOT_PROBED:
                    rows.append(
                        {
                            "tool": name,
                            "declared": [repr(r) for r in tool.scopes],
                            "skipped": NOT_PROBED[name],
                        }
                    )
                    continue
                if name not in PROBES and name not in DIRECT:
                    rows.append(
                        {
                            "tool": name,
                            "declared": [repr(r) for r in tool.scopes],
                            "skipped": "no probe written",
                        }
                    )
                    continue
                declared_text = [repr(r) if not isinstance(r, str) else r for r in tool.scopes]
                for key in _token_sets(tool):
                    if not set(key) <= granted:
                        rows.append(
                            {"tool": name, "scopes": key, "skipped": "scope not granted at connect"}
                        )
                        continue
                    if key not in tokens:
                        tokens[key] = await _mint(http, client_id, secret, refresh, list(key))
                    declared = await _call(http, name, tool, ctx, tokens[key])
                    without = await _call(http, name, tool, ctx, none_token)
                    ok = declared["outcome"] == "accepted" and without["outcome"] == "insufficient"
                    rows.append(
                        {
                            "tool": name,
                            "declared": declared_text,
                            "scopes": key,
                            "with": declared,
                            "without": without,
                            "ok": ok,
                        }
                    )
                    mark = "ok  " if ok else "FAIL"
                    short = ",".join(
                        s.removeprefix("https://www.googleapis.com/auth/") for s in key
                    )
                    print(
                        f"{mark} {name:46} {short:32} with {declared['status']} {declared['outcome']:12} "
                        f"without {without['status']} {without['outcome']}"
                    )
        finally:
            left = await _cleanup(http, full, ctx)

    failed = [r for r in rows if r.get("ok") is False]
    skipped = [r for r in rows if "skipped" in r]
    print(
        f"\n{sum(1 for r in rows if r.get('ok'))} tool-and-scope pairs pass, {len(failed)} fail, "
        f"{len(skipped)} not probed"
    )
    for r in skipped:
        print(f"  not probed: {r['tool']} {r.get('scopes', '')} ({r['skipped']})")
    if left:
        print(f"  NOT CLEANED UP: {left}")
    REPORT.write_text(
        json.dumps({"account": ctx.email, "run_at": ctx.stamp, "rows": rows}, indent=2)
    )
    print(f"report: {REPORT}")
    return 1 if failed or left else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("connect")
    c = sub.add_parser("check")
    c.add_argument("--account", required=True, help="the email the grant must belong to")
    c.add_argument("--only", default="", help="comma-separated tool-name prefixes, e.g. gforms.")
    args = ap.parse_args()
    if args.command == "connect":
        return asyncio.run(connect())
    return asyncio.run(check(args.account, args.only))


if __name__ == "__main__":
    sys.exit(main())
