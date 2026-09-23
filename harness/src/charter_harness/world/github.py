"""
GitHub, read and written directly, inside one sandbox repository.

The harness writes to exactly one repository, ``<owner>/<GITHUB_SANDBOX_REPO>``
(``harness-sandbox`` by default), which the guard is the other half of: the
model may not write anywhere the name does not start with ``harness-``. Inside
it every run gets its own label, branch prefix and directory, all carrying the
namespace, so runs do not collide and teardown knows what is its own.

Creating the repository needs a token with repository administration rights,
which a fine-grained token usually lacks; if it is missing and cannot be created
the error says what to do.
"""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Sequence
from typing import Any

from charter_harness.world._http import Http, WorldError, eventually

__all__ = ["GitHub"]


class GitHub:
    def __init__(self, http: Http, *, owner: str, sandbox_repo: str) -> None:
        self.http = http
        self.owner = owner
        self.repo = sandbox_repo

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repo}"

    def _r(self, path: str) -> str:
        return f"repos/{self.owner}/{self.repo}/{path.lstrip('/')}"

    # ---- repository

    async def ensure_sandbox(self) -> dict[str, Any]:
        try:
            return await self.http.json("GET", f"repos/{self.full_name}")
        except WorldError as exc:
            if exc.status != 404:
                raise
        try:
            return await self.http.json(
                "POST",
                "user/repos",
                json={
                    "name": self.repo,
                    # Public on purpose: firecrawl_to_linear has the model scrape a
                    # blob URL in this repo with no credentials, and Firecrawl cannot
                    # read a private repository. Nothing sensitive is ever written here.
                    "private": False,
                    "auto_init": True,
                    "description": "charter-harness sandbox — created and written by the scenario harness",
                },
            )
        except WorldError as exc:
            raise WorldError(
                f"The sandbox repository {self.full_name} does not exist and this token cannot create it "
                f"(a fine-grained PAT never can). Create it once by hand — PUBLIC, initialised with a "
                f"README — and give the token Issues, Contents and Pull requests read/write on it.",
                status=exc.status,
                body=exc.body,
            ) from exc

    async def default_branch(self) -> str:
        repo = await self.http.json("GET", f"repos/{self.full_name}")
        return repo.get("default_branch", "main")

    # ---- labels & issues

    async def label_ensure(self, name: str, color: str = "0e8a16") -> None:
        try:
            await self.http.json("POST", self._r("labels"), json={"name": name, "color": color})
        except WorldError as exc:
            if exc.status != 422:  # already exists
                raise

    async def label_delete(self, name: str) -> None:
        try:
            await self.http.request("DELETE", self._r(f"labels/{name}"))
        except WorldError as exc:
            if exc.status != 404:
                raise

    async def issue_create(
        self, *, title: str, body: str = "", labels: Sequence[str] = ()
    ) -> dict[str, Any]:
        return await self.http.json(
            "POST", self._r("issues"), json={"title": title, "body": body, "labels": list(labels)}
        )

    async def issues_list(
        self, *, labels: Sequence[str] = (), state: str = "all"
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"state": state, "per_page": 100}
        if labels:
            params["labels"] = ",".join(labels)
        items = await self.http.json("GET", self._r("issues"), params=params)
        return [i for i in items if "pull_request" not in i]

    async def await_issues_listed(
        self, *, label: str, numbers: Sequence[int], timeout: float = 45.0
    ) -> None:
        """Block until the label listing shows every issue in ``numbers``.

        A seed barrier: the listing endpoint can omit an issue for a few seconds
        after it is created, and the agent's first call is usually that listing.
        Times out silently — the run then proceeds and, if the lag persisted,
        fails in a way the trajectory makes obvious.
        """
        wanted = set(numbers)

        async def read() -> set[int]:
            return {i["number"] for i in await self.issues_list(labels=[label], state="open")}

        await eventually(read, lambda seen: wanted <= seen, timeout=timeout)

    async def issue_get(self, number: int) -> dict[str, Any]:
        return await self.http.json("GET", self._r(f"issues/{number}"))

    async def issue_comments(self, number: int) -> list[dict[str, Any]]:
        return await self.http.json(
            "GET", self._r(f"issues/{number}/comments"), params={"per_page": 100}
        )

    async def issue_close(self, number: int) -> None:
        try:
            await self.http.json("PATCH", self._r(f"issues/{number}"), json={"state": "closed"})
        except WorldError as exc:
            if exc.status != 404:
                raise

    async def issues_search_in_sandbox(
        self, text: str, *, state: str = "all", expect: int = 0
    ) -> list[dict[str, Any]]:
        """Issues in the sandbox mentioning ``text``.

        Filters a listing rather than using the search API, whose index lags by
        minutes. The listing itself is not read-your-writes either: an issue the
        agent opened a second before the read-back is sometimes absent for a few
        seconds. ``expect`` is how many matches the caller is waiting for; the
        read is repeated until that many appear or the wait runs out, and the
        judge sees whatever was there at the end.
        """
        needle = text.lower()

        async def read() -> list[dict[str, Any]]:
            items = await self.issues_list(state=state)
            return [
                i
                for i in items
                if needle in (i.get("title", "") + "\n" + (i.get("body") or "")).lower()
            ]

        if expect <= 0:
            return await read()
        return await eventually(read, lambda found: len(found) >= expect, timeout=30.0)

    # ---- contents, branches, pull requests

    async def content_put(
        self, *, path: str, content: str, message: str, branch: str
    ) -> dict[str, Any]:
        # Concurrent seeds on the same repo (two arms, two GitHub scenarios)
        # race the branch tip. GitHub answers 409 "is at X but expected Y";
        # refetch the blob SHA and try again rather than fail the seed.
        last: WorldError | None = None
        for attempt in range(5):
            existing_sha = None
            try:
                existing = await self.http.json(
                    "GET", self._r(f"contents/{path}"), params={"ref": branch}
                )
                existing_sha = existing.get("sha")
            except WorldError as exc:
                if exc.status != 404:
                    raise
            payload: dict[str, Any] = {
                "message": message,
                "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
                "branch": branch,
            }
            if existing_sha:
                payload["sha"] = existing_sha
            try:
                return await self.http.json("PUT", self._r(f"contents/{path}"), json=payload)
            except WorldError as exc:
                if exc.status != 409:
                    raise
                last = exc
                await asyncio.sleep(0.4 * (attempt + 1))
        assert last is not None
        raise last

    async def content_delete(self, *, path: str, branch: str, message: str) -> None:
        last: WorldError | None = None
        for attempt in range(5):
            try:
                existing = await self.http.json(
                    "GET", self._r(f"contents/{path}"), params={"ref": branch}
                )
                await self.http.request(
                    "DELETE",
                    self._r(f"contents/{path}"),
                    json={"message": message, "sha": existing["sha"], "branch": branch},
                )
                return
            except WorldError as exc:
                if exc.status == 404:
                    return
                if exc.status != 409:
                    raise
                last = exc
                await asyncio.sleep(0.4 * (attempt + 1))
        assert last is not None
        raise last

    async def branch_create(self, name: str, *, from_branch: str | None = None) -> str:
        base = from_branch or await self.default_branch()
        ref = await self.http.json("GET", self._r(f"git/ref/heads/{base}"))
        sha = ref["object"]["sha"]
        try:
            await self.http.json(
                "POST", self._r("git/refs"), json={"ref": f"refs/heads/{name}", "sha": sha}
            )
        except WorldError as exc:
            if exc.status != 422:  # exists
                raise
        return sha

    async def branch_delete(self, name: str) -> None:
        try:
            await self.http.request("DELETE", self._r(f"git/refs/heads/{name}"))
        except WorldError as exc:
            if exc.status not in (404, 422):
                raise

    async def pull_create(
        self, *, title: str, head: str, base: str, body: str = ""
    ) -> dict[str, Any]:
        return await self.http.json(
            "POST",
            self._r("pulls"),
            json={"title": title, "head": head, "base": base, "body": body},
        )

    async def pull_files(self, number: int) -> list[dict[str, Any]]:
        return await self.http.json(
            "GET", self._r(f"pulls/{number}/files"), params={"per_page": 100}
        )

    async def pull_close(self, number: int) -> None:
        try:
            await self.http.json("PATCH", self._r(f"pulls/{number}"), json={"state": "closed"})
        except WorldError as exc:
            if exc.status != 404:
                raise

    def raw_url(self, *, path: str, branch: str) -> str:
        return f"https://raw.githubusercontent.com/{self.owner}/{self.repo}/{branch}/{path}"

    def blob_url(self, *, path: str, branch: str) -> str:
        return f"https://github.com/{self.owner}/{self.repo}/blob/{branch}/{path}"
