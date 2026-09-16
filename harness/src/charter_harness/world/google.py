"""
Google, read and written directly: Gmail, Calendar, Sheets, Docs, and the one
Drive call that deletes what the seed created.

Every fixture carries the run's namespace where the API lets us put it —
label names, subjects, event summaries, spreadsheet and document titles — and
every read filters on it, so concurrent runs on the same account do not see
each other.
"""

from __future__ import annotations

import base64
from collections.abc import Sequence
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from typing import Any

from charter_harness.world._http import Http, WorldError, eventually

__all__ = ["Gmail", "Calendar", "Sheets", "Docs", "Drive"]


class Gmail:
    def __init__(self, http: Http) -> None:
        self.http = http

    # ---- labels
    async def labels_list(self) -> list[dict[str, Any]]:
        data = await self.http.json("GET", "gmail/v1/users/me/labels")
        return data.get("labels", [])

    async def label_by_name(self, name: str) -> dict[str, Any] | None:
        for label in await self.labels_list():
            if label["name"].lower() == name.lower():
                return label
        return None

    async def label_create(self, name: str) -> dict[str, Any]:
        existing = await self.label_by_name(name)
        if existing:
            return existing
        return await self.http.json(
            "POST",
            "gmail/v1/users/me/labels",
            json={"name": name, "labelListVisibility": "labelShow", "messageListVisibility": "show"},
        )

    async def label_delete(self, label_id: str) -> None:
        try:
            await self.http.request("DELETE", f"gmail/v1/users/me/labels/{label_id}")
        except WorldError as exc:
            if exc.status != 404:
                raise

    # ---- messages
    async def message_insert(
        self,
        *,
        sender: str,
        to: str,
        subject: str,
        body: str,
        label_ids: Sequence[str] = ("INBOX",),
        thread_id: str | None = None,
        in_reply_to: str | None = None,
    ) -> dict[str, Any]:
        """Put a message straight into the mailbox (``messages.insert``): no
        sending, no SMTP, deterministic headers."""
        msg = EmailMessage()
        msg["From"] = sender
        msg["To"] = to
        msg["Subject"] = subject
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid(domain="harness.invalid")
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
            msg["References"] = in_reply_to
        msg.set_content(body)
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
        payload: dict[str, Any] = {"raw": raw, "labelIds": list(label_ids)}
        if thread_id:
            payload["threadId"] = thread_id
        created = await self.http.json(
            "POST", "gmail/v1/users/me/messages", params={"internalDateSource": "dateHeader"}, json=payload
        )
        created["_message_id_header"] = msg["Message-ID"]
        return created

    async def messages_list(
        self, *, q: str | None = None, label_ids: Sequence[str] = (), max_results: int = 100
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"maxResults": max_results}
        if q:
            params["q"] = q
        if label_ids:
            params["labelIds"] = list(label_ids)
        data = await self.http.json("GET", "gmail/v1/users/me/messages", params=params)
        return data.get("messages", []) or []

    async def await_labelled(self, label_id: str, ids: Sequence[str], *, timeout: float = 90.0) -> list[dict[str, Any]]:
        """Wait until ``messages.list`` by label returns every seeded message; label
        propagation after ``messages.insert`` is not instantaneous."""
        wanted = set(ids)
        got = await eventually(
            lambda: self.messages_list(label_ids=[label_id]), lambda ms: wanted <= {m["id"] for m in ms}, timeout=timeout, interval=3.0
        )
        missing = wanted - {m["id"] for m in got}
        if missing:
            raise WorldError(f"{len(missing)} Gmail message(s) not listed under label {label_id} after {timeout:.0f}s")
        return got

    async def message_get(self, message_id: str, *, fmt: str = "metadata") -> dict[str, Any]:
        params = {"format": fmt}
        if fmt == "metadata":
            params["metadataHeaders"] = ["From", "To", "Subject", "Message-ID", "In-Reply-To"]
        return await self.http.json("GET", f"gmail/v1/users/me/messages/{message_id}", params=params)

    async def message_modify(
        self, message_id: str, *, add: Sequence[str] = (), remove: Sequence[str] = ()
    ) -> dict[str, Any]:
        return await self.http.json(
            "POST",
            f"gmail/v1/users/me/messages/{message_id}/modify",
            json={"addLabelIds": list(add), "removeLabelIds": list(remove)},
        )

    async def message_trash(self, message_id: str) -> None:
        try:
            await self.http.request("POST", f"gmail/v1/users/me/messages/{message_id}/trash")
        except WorldError as exc:
            if exc.status != 404:
                raise

    async def thread_get(self, thread_id: str) -> dict[str, Any]:
        return await self.http.json(
            "GET",
            f"gmail/v1/users/me/threads/{thread_id}",
            params={"format": "metadata", "metadataHeaders": ["From", "To", "Subject", "Message-ID"]},
        )

    # ---- drafts
    async def drafts_list(self) -> list[dict[str, Any]]:
        data = await self.http.json("GET", "gmail/v1/users/me/drafts", params={"maxResults": 100})
        return data.get("drafts", []) or []

    async def draft_get(self, draft_id: str) -> dict[str, Any] | None:
        # drafts.list is a snapshot; a concurrent teardown (or the agent itself)
        # can delete an id before we fetch it. Treat that as "gone", not a
        # harness error — observe will simply not see that draft.
        try:
            return await self.http.json("GET", f"gmail/v1/users/me/drafts/{draft_id}", params={"format": "full"})
        except WorldError as exc:
            if exc.status == 404:
                return None
            raise

    async def draft_delete(self, draft_id: str) -> None:
        try:
            await self.http.request("DELETE", f"gmail/v1/users/me/drafts/{draft_id}")
        except WorldError as exc:
            if exc.status != 404:
                raise


def header(message: dict[str, Any], name: str) -> str:
    for h in (message.get("payload") or {}).get("headers", []):
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def body_text(message: dict[str, Any]) -> str:
    """Best-effort plain text of a ``format=full`` message."""
    payload = message.get("payload") or {}

    def walk(part: dict[str, Any]) -> str:
        data = (part.get("body") or {}).get("data")
        if part.get("mimeType", "").startswith("text/plain") and data:
            return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
        for sub in part.get("parts", []) or []:
            found = walk(sub)
            if found:
                return found
        if data and not part.get("parts"):
            return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
        return ""

    return walk(payload)


class Calendar:
    def __init__(self, http: Http) -> None:
        self.http = http

    async def event_insert(
        self,
        *,
        summary: str,
        start: str,
        end: str,
        timezone: str,
        description: str = "",
        calendar_id: str = "primary",
    ) -> dict[str, Any]:
        return await self.http.json(
            "POST",
            f"calendar/v3/calendars/{calendar_id}/events",
            json={
                "summary": summary,
                "description": description,
                "start": {"dateTime": start, "timeZone": timezone},
                "end": {"dateTime": end, "timeZone": timezone},
            },
        )

    async def events_list(
        self,
        *,
        q: str | None = None,
        time_min: str | None = None,
        time_max: str | None = None,
        calendar_id: str = "primary",
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"singleEvents": True, "orderBy": "startTime", "maxResults": 250, "showDeleted": False}
        if q:
            params["q"] = q
        if time_min:
            params["timeMin"] = time_min
        if time_max:
            params["timeMax"] = time_max
        data = await self.http.json("GET", f"calendar/v3/calendars/{calendar_id}/events", params=params)
        return data.get("items", []) or []

    async def await_events(
        self, *, q: str, ids: Sequence[str], time_min: str, time_max: str, timeout: float = 90.0
    ) -> list[dict[str, Any]]:
        """Wait until the free-text ``q`` search returns every seeded event."""
        wanted = set(ids)
        got = await eventually(
            lambda: self.events_list(q=q, time_min=time_min, time_max=time_max),
            lambda es: wanted <= {e["id"] for e in es},
            timeout=timeout,
            interval=3.0,
        )
        missing = wanted - {e["id"] for e in got}
        if missing:
            raise WorldError(f"{len(missing)} Calendar event(s) not found by q={q!r} after {timeout:.0f}s")
        return got

    async def events_list_eventually(
        self, *, q: str, time_min: str, time_max: str, at_least: int, timeout: float = 45.0
    ) -> list[dict[str, Any]]:
        """For events the model created: retry the search until it returns ``at_least``."""
        return await eventually(
            lambda: self.events_list(q=q, time_min=time_min, time_max=time_max),
            lambda es: len([e for e in es if e.get("status") != "cancelled"]) >= at_least,
            timeout=timeout,
            interval=3.0,
        )

    async def event_get(self, event_id: str, *, calendar_id: str = "primary") -> dict[str, Any] | None:
        try:
            return await self.http.json("GET", f"calendar/v3/calendars/{calendar_id}/events/{event_id}")
        except WorldError as exc:
            if exc.status in (404, 410):
                return None
            raise

    async def event_delete(self, event_id: str, *, calendar_id: str = "primary") -> None:
        try:
            await self.http.request("DELETE", f"calendar/v3/calendars/{calendar_id}/events/{event_id}")
        except WorldError as exc:
            if exc.status not in (404, 410):
                raise


class Sheets:
    def __init__(self, http: Http) -> None:
        self.http = http

    async def spreadsheet_create(self, title: str, *, sheet_title: str = "Sheet1") -> dict[str, Any]:
        return await self.http.json(
            "POST",
            "v4/spreadsheets",
            json={"properties": {"title": title}, "sheets": [{"properties": {"title": sheet_title}}]},
        )

    async def values_update(self, spreadsheet_id: str, range_: str, values: list[list[Any]]) -> None:
        await self.http.json(
            "PUT",
            f"v4/spreadsheets/{spreadsheet_id}/values/{range_}",
            params={"valueInputOption": "USER_ENTERED"},
            json={"range": range_, "majorDimension": "ROWS", "values": values},
        )

    async def values_get(self, spreadsheet_id: str, range_: str) -> list[list[str]]:
        data = await self.http.json("GET", f"v4/spreadsheets/{spreadsheet_id}/values/{range_}")
        return data.get("values", []) or []


class Docs:
    def __init__(self, http: Http) -> None:
        self.http = http

    async def document_create(self, title: str, *, text: str = "") -> dict[str, Any]:
        doc = await self.http.json("POST", "v1/documents", json={"title": title})
        if text:
            await self.http.json(
                "POST",
                f"v1/documents/{doc['documentId']}:batchUpdate",
                json={"requests": [{"insertText": {"location": {"index": 1}, "text": text}}]},
            )
        return doc

    async def document_get(self, document_id: str) -> dict[str, Any] | None:
        try:
            return await self.http.json("GET", f"v1/documents/{document_id}")
        except WorldError as exc:
            if exc.status == 404:
                return None
            raise

    @staticmethod
    def text_of(document: dict[str, Any]) -> str:
        out: list[str] = []
        for element in (document.get("body") or {}).get("content", []):
            paragraph = element.get("paragraph")
            if not paragraph:
                continue
            for run in paragraph.get("elements", []):
                text_run = run.get("textRun")
                if text_run:
                    out.append(text_run.get("content", ""))
        return "".join(out)


class Drive:
    def __init__(self, http: Http) -> None:
        self.http = http

    async def files_list(self, *, name_contains: str) -> list[dict[str, Any]]:
        q = f"name contains '{name_contains}' and trashed = false"
        data = await self.http.json(
            "GET", "drive/v3/files", params={"q": q, "fields": "files(id,name,mimeType)", "pageSize": 100}
        )
        return data.get("files", []) or []

    async def files_list_eventually(self, *, name_contains: str, at_least: int = 1, timeout: float = 45.0) -> list[dict[str, Any]]:
        """For files the model created: Drive search can lag a fresh document."""
        return await eventually(
            lambda: self.files_list(name_contains=name_contains), lambda fs: len(fs) >= at_least, timeout=timeout, interval=3.0
        )

    async def file_delete(self, file_id: str) -> None:
        try:
            await self.http.request("DELETE", f"drive/v3/files/{file_id}")
        except WorldError as exc:
            if exc.status not in (404, 403):
                raise
