"""
Slack Web API, read and written directly, in one channel.

The bot posts fixture threads into the harness channel and reads the channel's
history back. Everything the seed posts is prefixed with the namespace, and
teardown deletes exactly those messages.
"""

from __future__ import annotations

from typing import Any

from charter_harness.world._http import Http, WorldError

__all__ = ["Slack"]


class Slack:
    def __init__(self, http: Http, *, channel_name: str) -> None:
        self.http = http
        self.channel_name = channel_name.lstrip("#")
        self._channel_id: str | None = None

    async def call(
        self, method: str, *, params: dict[str, Any] | None = None, json: Any = None
    ) -> dict[str, Any]:
        verb = "POST" if json is not None else "GET"
        data = await self.http.json(verb, method, params=params, json=json)
        if not data.get("ok"):
            raise WorldError(
                f"Slack {method} failed: {data.get('error')}", status=200, body=str(data)[:2000]
            )
        return data

    async def channel_id(self) -> str:
        if self._channel_id is None:
            cursor = None
            while True:
                params: dict[str, Any] = {
                    "limit": 200,
                    "types": "public_channel,private_channel",
                    "exclude_archived": True,
                }
                if cursor:
                    params["cursor"] = cursor
                data = await self.call("conversations.list", params=params)
                for channel in data.get("channels", []):
                    if channel["name"] == self.channel_name:
                        self._channel_id = str(channel["id"])
                        return str(self._channel_id)
                cursor = (data.get("response_metadata") or {}).get("next_cursor")
                if not cursor:
                    break
            raise WorldError(f"No Slack channel named #{self.channel_name} visible to the bot")
        return str(self._channel_id)

    async def post(self, text: str, *, thread_ts: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"channel": await self.channel_id(), "text": text}
        if thread_ts:
            payload["thread_ts"] = thread_ts
        return await self.call("chat.postMessage", json=payload)

    async def history(self, *, oldest: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"channel": await self.channel_id(), "limit": limit}
        if oldest:
            params["oldest"] = oldest
        data = await self.call("conversations.history", params=params)
        return data.get("messages", [])

    async def replies(self, thread_ts: str) -> list[dict[str, Any]]:
        data = await self.call(
            "conversations.replies",
            params={"channel": await self.channel_id(), "ts": thread_ts, "limit": 200},
        )
        return data.get("messages", [])

    async def delete(self, ts: str) -> None:
        try:
            await self.call("chat.delete", json={"channel": await self.channel_id(), "ts": ts})
        except WorldError:
            pass

    async def delete_thread(self, thread_ts: str) -> None:
        for message in await self.replies(thread_ts):
            await self.delete(message["ts"])
