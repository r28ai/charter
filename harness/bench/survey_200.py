"""Live samples for the survey of failures that come back as HTTP 200.

The survey itself is documentary: each row cites the vendor's own page. This
script confirms a sample of those rows against the real APIs, by sending a
request the vendor documents as a failure and recording the status code and the
fields that carry the failure. It talks to the APIs with plain ``httpx``, not
through Charter, because the question is what the API answers, not what any
tool layer makes of it.

Every probe is read-only or has no effect: a lookup of an id that does not
exist, or a scrape of a page that does not exist in the public sandbox repo.
Firecrawl and Tavily each spend one credit.

    cd harness && .venv/bin/python bench/survey_200.py

Writes ``results/bench/survey_200_live.json``. Prints no credential.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

import httpx

from charter_harness.settings import load

OUT = Path(__file__).resolve().parent.parent / "results" / "bench" / "survey_200_live.json"
MISSING_ID = "00000000-0000-0000-0000-000000000000"


def _missing_page(owner: str, repo: str) -> str:
    return f"https://github.com/{owner}/{repo}/blob/main/no-such-file-charter-survey"


async def slack(c: httpx.AsyncClient, s) -> dict[str, Any]:
    r = await c.post(
        "https://slack.com/api/conversations.info",
        headers={"Authorization": f"Bearer {s.slack_bot_token}"},
        data={"channel": "C00000000000"},
    )
    body = r.json()
    return {"status": r.status_code, "ok": body.get("ok"), "error": body.get("error")}


async def linear(c: httpx.AsyncClient, s) -> dict[str, Any]:
    r = await c.post(
        "https://api.linear.app/graphql",
        headers={"Authorization": s.linear_api_key},
        json={"query": f'{{ issue(id: "{MISSING_ID}") {{ id title }} }}'},
    )
    body = r.json()
    errors = body.get("errors") or []
    return {
        "status": r.status_code,
        "data": body.get("data"),
        "errors": [
            {"message": e.get("message"), "code": (e.get("extensions") or {}).get("code")}
            for e in errors
        ],
    }


async def firecrawl(c: httpx.AsyncClient, s) -> dict[str, Any]:
    r = await c.post(
        "https://api.firecrawl.dev/v2/scrape",
        headers={"Authorization": f"Bearer {s.firecrawl_api_key}"},
        json={
            "url": _missing_page(s.github_owner, s.github_sandbox_repo),
            "formats": ["markdown"],
        },
        timeout=90,
    )
    body = r.json()
    meta = (body.get("data") or {}).get("metadata") or {}
    return {
        "status": r.status_code,
        "success": body.get("success"),
        "metadata.statusCode": meta.get("statusCode"),
        "metadata.error": meta.get("error"),
        "markdown_chars": len((body.get("data") or {}).get("markdown") or ""),
    }


async def tavily(c: httpx.AsyncClient, s) -> dict[str, Any]:
    r = await c.post(
        "https://api.tavily.com/extract",
        headers={"Authorization": f"Bearer {s.tavily_api_key}"},
        json={"urls": [_missing_page(s.github_owner, s.github_sandbox_repo)]},
        timeout=90,
    )
    body = r.json()
    return {
        "status": r.status_code,
        "results": len(body.get("results") or []),
        "failed_results": body.get("failed_results"),
    }


async def stripe(c: httpx.AsyncClient, s) -> dict[str, Any]:
    """The control: Stripe answers a missing object with a 4xx."""
    r = await c.get(
        "https://api.stripe.com/v1/refunds/re_doesnotexist000000000000",
        auth=(s.stripe_api_key, ""),
    )
    err = r.json().get("error") or {}
    return {"status": r.status_code, "type": err.get("type"), "code": err.get("code")}


async def github(c: httpx.AsyncClient, s) -> dict[str, Any]:
    """The control on the REST side: a missing issue is a 404."""
    r = await c.get(
        f"https://api.github.com/repos/{s.github_owner}/{s.github_sandbox_repo}/issues/999999",
        headers={
            "Authorization": f"Bearer {s.github_token}",
            "Accept": "application/vnd.github+json",
        },
    )
    return {"status": r.status_code, "message": r.json().get("message")}


PROBES = {
    "slack": ("slack", slack, "conversations.info on a channel that does not exist"),
    "linear": ("linear", linear, "issue(id:) for an id that does not exist"),
    "firecrawl": ("firecrawl", firecrawl, "scrape of a page that answers 404"),
    "tavily": ("tavily", tavily, "extract of a page that answers 404"),
    "stripe": ("stripe", stripe, "refund that does not exist (control)"),
    "github": ("github", github, "issue that does not exist (control)"),
}


async def main() -> None:
    s = load()
    have = s.available()
    out: dict[str, Any] = {
        "run_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "probes": {},
    }
    async with httpx.AsyncClient(timeout=30) as c:
        for name, (provider, probe, what) in PROBES.items():
            if provider not in have:
                out["probes"][name] = {"what": what, "skipped": "provider not configured"}
                continue
            try:
                result = await probe(c, s)
            except Exception as exc:  # recorded, not hidden
                result = {"exception": f"{type(exc).__name__}: {exc}"}
            out["probes"][name] = {"what": what, **result}
            print(f"{name:10} {json.dumps(result)[:300]}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    asyncio.run(main())
