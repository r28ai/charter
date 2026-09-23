"""
The raw arm: the API glue people write first, as the control.

One tool per provider. It knows the base URL, carries the same credentials the
Charter arm uses, and sends whatever the model gives it — method, path, query,
body — returning the response body as text. That is the whole tool. Paths,
casing, base64/RFC 822 assembly, GraphQL documents, form encoding, error
envelopes inside a 200, and the size of what comes back are the model's
problem, which is exactly the work the boundary claims to take off the model.

The endpoint list in each tool's description is *derived* from the Charter
pack's tools (method, ``url_template``, description), so the control arm knows
about the same endpoints and no more — nobody hand-picked them. The guard
enforces that set from the same derivation; see :mod:`charter_harness.guard`.

Two deliberate choices, both documented in the report:

- A response larger than :data:`RAW_RESPONSE_CAP` bytes is cut there and the
  cut is recorded. Without a cap a single 1 MB response would end a run on a
  context error; with it, the model at least sees the first 100 KB. It is the
  cap a careful engineer would add to the same glue.
- A non-2xx status is raised as a ``ToolError`` (the model reads status and
  body), mirroring the Charter arm where ``APIError`` does the same. A 200 that
  carries a failure in its body is returned as a success, because nothing in
  this arm knows the difference.
"""

from __future__ import annotations

import re
import time
from collections.abc import Sequence
from dataclasses import dataclass
from re import Pattern
from typing import Any

import httpx
from inspect_ai.tool import ToolDef, ToolError, ToolParams
from inspect_ai.util import JSONSchema

from charter_harness._client import shared_client
from charter_harness.arms.base import register
from charter_harness.arms.charter_arm import pack_tools
from charter_harness.arms.ledger import record_raw_call
from charter_harness.arms.ownership import record_raw_creation
from charter_harness.context import run_context
from charter_harness.settings import Wiring

__all__ = [
    "RAW_RESPONSE_CAP",
    "Endpoint",
    "endpoints_for",
    "template_to_regex",
    "normalise_path",
    "RawArm",
]

RAW_RESPONSE_CAP = 100_000

# Packs whose tools are all one POST to one GraphQL endpoint. Their raw tool
# takes a document, not a path.
GRAPHQL_PACKS = {"linear", "shopify"}

# Wire conventions the raw tool has to state, because the Charter pack states
# them in its declaration and the model on this arm has nothing else.
_NOTES: dict[str, str] = {
    "gmail": (
        "Query parameters are camelCase (maxResults, labelIds, pageToken). Write endpoints "
        'that take a message (drafts, send) expect {"raw": <base64url-encoded RFC 822 message>}.'
    ),
    "gcalendar": "Query parameters are camelCase (timeMin, timeMax, singleEvents, orderBy). Timestamps are RFC 3339.",
    "gsheets": "Query parameters are camelCase (valueInputOption, majorDimension). Ranges use A1 notation.",
    "gdocs": "Edits go through documents.batchUpdate with a JSON list of requests.",
    "gdrive": "Query parameters are camelCase (pageSize, supportsAllDrives, mimeType). files.list returns trashed files unless q includes trashed = false.",
    "stripe": (
        "The body is sent as application/x-www-form-urlencoded, so give a flat object; nested "
        'fields use bracket notation, e.g. {"metadata[harness]": "x", "expand[]": "data.customer"}. '
        "Amounts are integers in the smallest currency unit."
    ),
    "github": "JSON bodies. Repository endpoints take owner and repo in the path.",
    "slack": (
        "Reads are GET with query parameters, writes are POST with a JSON body. Slack returns HTTP 200 "
        'with {"ok": false, "error": ...} when a call fails.'
    ),
    "firecrawl": 'JSON bodies. Responses carry {"success": ..., "data": ...}.',
}


@dataclass(frozen=True)
class Endpoint:
    method: str
    template: str
    description: str

    @property
    def regex(self) -> Pattern[str]:
        return template_to_regex(self.template)


def template_to_regex(template: str) -> Pattern[str]:
    """``gmail/v1/users/{userId}/threads/{id}`` -> a regex matching a filled path."""
    parts = re.split(r"\{[^}]+\}", template.strip("/"))
    pattern = "[^/?#]+".join(re.escape(p) for p in parts)
    return re.compile("^" + pattern + "$")


def normalise_path(path: str, base_url: str) -> str:
    """The path the model gave, as the bare template-shaped path the guard compares."""
    p = path.strip()
    if base_url and p.startswith(base_url):
        p = p[len(base_url) :]
    elif p.startswith("http://") or p.startswith("https://"):
        p = re.sub(r"^https?://[^/]+/", "", p)
    p = p.split("?", 1)[0].split("#", 1)[0]
    return p.strip("/")


def endpoints_for(pack: str) -> list[Endpoint]:
    """The endpoints a pack's (non-withheld) tools reach, one per tool."""
    seen: dict[tuple[str, str], Endpoint] = {}
    for tool in pack_tools(pack):
        key = (tool.method, tool.url_template.strip("/"))
        if key not in seen:
            seen[key] = Endpoint(tool.method, tool.url_template.strip("/"), tool.description)
    return list(seen.values())


def _operations_for(pack: str) -> list[tuple[str, str]]:
    """GraphQL packs: the operation each tool runs, named the way the API names it."""
    ops: list[tuple[str, str]] = []
    for tool in pack_tools(pack):
        document = (tool.static_body or {}).get("query", "")
        # The operation is the first field selected after the opening brace of
        # the top-level query/mutation, e.g. `mutation ... { issueCreate(` .
        match = re.search(r"\{\s*([A-Za-z_][A-Za-z0-9_]*)", document)
        op = match.group(1) if match else tool.name
        ops.append((op, tool.description))
    return ops


def _base_url(pack: str, wiring: Wiring) -> str:
    module = __import__(f"charter.packs.{pack}", fromlist=["BASE_URL"])
    if pack == "shopify":
        return f"https://{wiring.settings.shopify_shop}/"
    return str(module.BASE_URL)


async def _auth_headers(pack: str, wiring: Wiring) -> dict[str, str]:
    s = wiring.settings
    if pack in ("gmail", "gcalendar", "gsheets", "gdocs", "gdrive"):
        return {"Authorization": f"Bearer {await wiring.google_token()}"}
    if pack == "stripe":
        from charter.packs import stripe

        return {"Authorization": f"Bearer {s.stripe_api_key}", "Stripe-Version": stripe.API_VERSION}
    if pack == "github":
        from charter.packs import github

        return {"Authorization": f"Bearer {s.github_token}", **github.GITHUB_HEADERS}
    if pack == "linear":
        return {"Authorization": s.linear_api_key or ""}
    if pack == "shopify":
        return {"X-Shopify-Access-Token": s.shopify_access_token or ""}
    if pack == "slack":
        return {"Authorization": f"Bearer {s.slack_bot_token}"}
    if pack == "firecrawl":
        return {"Authorization": f"Bearer {s.firecrawl_api_key}"}
    raise ValueError(f"no raw-arm auth for pack {pack!r}")


def _cap(text: str) -> tuple[str, bool]:
    raw = text.encode("utf-8")
    if len(raw) <= RAW_RESPONSE_CAP:
        return text, False
    head = raw[:RAW_RESPONSE_CAP].decode("utf-8", errors="ignore")
    return (
        head
        + f"\n... [truncated: response was {len(raw)} bytes; showing the first {RAW_RESPONSE_CAP}]",
        True,
    )


def _rest_description(pack: str, base_url: str, endpoints: Sequence[Endpoint]) -> str:
    lines = [
        f"Raw HTTP access to the {pack} API. Base URL: {base_url} — give `path` relative to it, "
        "with path parameters filled in. Authentication headers are added for you.",
        "`query` is a JSON object of query-string parameters; `body` is the request body for "
        "POST/PUT/PATCH/DELETE. The full response body is returned as text.",
        _NOTES.get(pack, ""),
        "Endpoints:",
    ]
    for ep in endpoints:
        lines.append(f"- {ep.method} {ep.template} — {ep.description}")
    return "\n".join(line for line in lines if line)


def _graphql_description(pack: str, url: str, ops: Sequence[tuple[str, str]]) -> str:
    lines = [
        f"Raw access to the {pack} GraphQL API at {url}. Authentication headers are added for you.",
        "Send a GraphQL document in `query` and its variables in `variables`; the full JSON "
        "response (data and errors) is returned as text. You write the selection sets.",
        "Operations available:",
    ]
    for op, description in ops:
        lines.append(f"- {op} — {description}")
    if pack == "linear":
        lines.append(
            "Linear returns HTTP 200 with an `errors` array for a rejected document, and "
            "`success: false` inside a mutation payload it declined."
        )
    if pack == "shopify":
        lines.append("Shopify mutations report validation failures in `userErrors`, with HTTP 200.")
    return "\n".join(lines)


def _rest_params(pack: str) -> ToolParams:
    body_desc = (
        "Form fields (flat object, bracket notation for nesting)."
        if pack == "stripe"
        else "JSON request body."
    )
    return ToolParams(
        properties={
            "method": JSONSchema(
                type="string",
                enum=["GET", "POST", "PUT", "PATCH", "DELETE"],
                description="HTTP method.",
            ),
            "path": JSONSchema(
                type="string", description="Path relative to the base URL, parameters filled in."
            ),
            "query": JSONSchema(
                anyOf=[
                    JSONSchema(type="object", additionalProperties=True),
                    JSONSchema(type="null"),
                ],
                description="Query-string parameters.",
            ),
            "body": JSONSchema(
                anyOf=[
                    JSONSchema(type="object", additionalProperties=True),
                    JSONSchema(type="null"),
                ],
                description=body_desc,
            ),
        },
        required=["method", "path"],
        additionalProperties=False,
    )


def _graphql_params() -> ToolParams:
    return ToolParams(
        properties={
            "query": JSONSchema(type="string", description="The GraphQL document."),
            "variables": JSONSchema(
                anyOf=[
                    JSONSchema(type="object", additionalProperties=True),
                    JSONSchema(type="null"),
                ],
                description="Variables for the document.",
            ),
        },
        required=["query"],
        additionalProperties=False,
    )


def _render_response(response: httpx.Response) -> str:
    return response.text


def _rest_tool(pack: str, wiring: Wiring) -> ToolDef:
    base_url = _base_url(pack, wiring)
    endpoints = endpoints_for(pack)
    tool_name = f"{pack}_api"

    async def call(**kwargs: Any) -> str:
        method = str(kwargs.get("method", "GET")).upper()
        path = normalise_path(str(kwargs.get("path", "")), base_url)
        query = kwargs.get("query") or None
        body = kwargs.get("body")
        started = time.perf_counter()
        status: int | None = None
        try:
            headers = await _auth_headers(pack, wiring)
            request: dict[str, Any] = {"params": query, "headers": headers}
            if body is not None and method in ("POST", "PUT", "PATCH", "DELETE"):
                if pack == "stripe":
                    request["data"] = body
                else:
                    request["json"] = body
            client = shared_client()
            response = await client.request(method, base_url + path, **request)
            status = response.status_code
            text = _render_response(response)
            shown, truncated = _cap(text)
            ok = 200 <= status < 300
            record_raw_call(
                tool=tool_name,
                provider=pack,
                method=method,
                path=path,
                status_code=status,
                ok=ok,
                total_ms=(time.perf_counter() - started) * 1000,
                payload_bytes=len(response.content),
                context_bytes=len(shown.encode("utf-8")),
                truncated=truncated,
                error_type=None if ok else "http_error",
            )
            if not ok:
                raise ToolError(f"HTTP {status} {method} {path}\n{shown}")
            record_raw_creation(pack, method, path, shown)
            return shown
        except ToolError:
            raise
        except Exception as exc:
            record_raw_call(
                tool=tool_name,
                provider=pack,
                method=method,
                path=path,
                status_code=status,
                ok=False,
                total_ms=(time.perf_counter() - started) * 1000,
                payload_bytes=None,
                context_bytes=None,
                truncated=False,
                error_type="transport_error",
            )
            raise ToolError(f"{type(exc).__name__}: {exc}") from exc

    call.__name__ = tool_name
    return ToolDef(
        call,
        name=tool_name,
        description=_rest_description(pack, base_url, endpoints),
        parameters=_rest_params(pack),
        max_output=0,
    )


def _graphql_tool(pack: str, wiring: Wiring) -> ToolDef:
    if pack == "linear":
        from charter.packs import linear

        url = linear.BASE_URL + linear.GRAPHQL_PATH
    else:
        url = wiring.shopify_graphql_url
    tool_name = f"{pack}_graphql"
    ops = _operations_for(pack)

    async def call(**kwargs: Any) -> str:
        document = str(kwargs.get("query", ""))
        variables = kwargs.get("variables") or {}
        started = time.perf_counter()
        status: int | None = None
        try:
            headers = await _auth_headers(pack, wiring)
            client = shared_client()
            response = await client.post(
                url, json={"query": document, "variables": variables}, headers=headers
            )
            status = response.status_code
            shown, truncated = _cap(response.text)
            ok = 200 <= status < 300
            record_raw_call(
                tool=tool_name,
                provider=pack,
                method="POST",
                path="graphql",
                status_code=status,
                ok=ok,
                total_ms=(time.perf_counter() - started) * 1000,
                payload_bytes=len(response.content),
                context_bytes=len(shown.encode("utf-8")),
                truncated=truncated,
                error_type=None if ok else "http_error",
            )
            if not ok:
                raise ToolError(f"HTTP {status}\n{shown}")
            return shown
        except ToolError:
            raise
        except Exception as exc:
            record_raw_call(
                tool=tool_name,
                provider=pack,
                method="POST",
                path="graphql",
                status_code=status,
                ok=False,
                total_ms=(time.perf_counter() - started) * 1000,
                payload_bytes=None,
                context_bytes=None,
                truncated=False,
                error_type="transport_error",
            )
            raise ToolError(f"{type(exc).__name__}: {exc}") from exc

    call.__name__ = tool_name
    return ToolDef(
        call,
        name=tool_name,
        description=_graphql_description(pack, url, ops),
        parameters=_graphql_params(),
        max_output=0,
    )


def raw_tool_name(pack: str) -> str:
    return f"{pack}_graphql" if pack in GRAPHQL_PACKS else f"{pack}_api"


class RawArm:
    name = "raw"

    def tools(self, packs: Sequence[str], wiring: Wiring) -> list[ToolDef]:
        defs: list[ToolDef] = []
        index: dict[str, list[str]] = {}
        for pack in packs:
            defs.append(
                _graphql_tool(pack, wiring) if pack in GRAPHQL_PACKS else _rest_tool(pack, wiring)
            )
            index[raw_tool_name(pack)] = [pack, raw_tool_name(pack)]
        ctx = run_context()
        ctx.arm = self.name
        ctx.tool_index = index
        return defs


register(RawArm())
