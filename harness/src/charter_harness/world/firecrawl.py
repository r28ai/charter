"""
Firecrawl, called directly — only to confirm a scrape target resolves.

Scenarios that involve Firecrawl point it at a file the GitHub seed just wrote,
so there is nothing to seed or tear down here; the world client exists so a
scenario can check the target is reachable before the model is asked to scrape it.
"""

from __future__ import annotations

from typing import Any

from charter_harness.world._http import Http

__all__ = ["Firecrawl"]


class Firecrawl:
    def __init__(self, http: Http) -> None:
        self.http = http

    async def scrape_markdown(self, url: str) -> dict[str, Any]:
        data = await self.http.json("POST", "scrape", json={"url": url, "formats": ["markdown"]})
        return data.get("data", data)
