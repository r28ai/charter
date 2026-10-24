#!/usr/bin/env python
"""Does every Stripe tool declare the restricted-key permission Stripe itself names?

Deliberately not a test: the suite is offline by rule. Stripe refuses a restricted
key a call it has no permission for before running it, and names the permission
that would have let it through: "Having the 'rak_charge_read' permission would
allow this request to continue." So a test-mode restricted key with **every
permission set to None** is enough to read the answer for every tool, and it can
change nothing: every call it sends is refused.

    STRIPE_PERMISSION_PROBE_KEY=rk_test_... uv run python scripts/live_stripe_permissions_check.py

Create the key in a sandbox at dashboard.stripe.com/test/apikeys, "Create
restricted key", leaving every permission at None. Stripe will not save a key with
none at all, so give it one no tool here uses (3D Secure, Read, on 2026-10-24). The run refuses a key that is
not `rk_test_`, and stops the moment any call is answered with a success. Prints
no key.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import httpx

from charter import CharterError, InsufficientScope, Tool, ToolValidationError
from charter.auth import AnyOf, StaticTokenProvider
from charter.packs import stripe

LIVE = Path(os.environ.get("CHARTER_LIVE_DIR", Path.home() / ".charter/live"))
REPORT = LIVE / "stripe-permissions-check.json"
MISSING = "charter_scope_probe_missing"


def _placeholder(name: str, schema: dict[str, Any]) -> Any:
    if "enum" in schema:
        return schema["enum"][0]
    kind = schema.get("type")
    if kind == "integer":
        return 100
    if kind == "number":
        return 1.0
    if kind == "boolean":
        return False
    if kind == "array":
        return []
    if kind == "object":
        return {}
    if name == "currency":
        return "usd"
    if name in ("query",):
        return "email:'probe@example.com'"
    return f"{MISSING}_{name}"


def _args(tool: Tool) -> dict[str, Any]:
    schema = tool.to_json_schema()["parameters"]
    defs = schema.get("$defs", {})

    def resolve(s: dict[str, Any]) -> dict[str, Any]:
        while "$ref" in s:
            s = defs[s["$ref"].split("/")[-1]]
        if "anyOf" in s:
            s = next((resolve(a) for a in s["anyOf"] if a.get("type") != "null"), s)
        return s

    def fill(s: dict[str, Any]) -> dict[str, Any]:
        s = resolve(s)
        out: dict[str, Any] = {}
        for name in s.get("required", []):
            prop = resolve(s["properties"][name])
            out[name] = (
                fill(prop)
                if prop.get("type") == "object" and "properties" in prop
                else _placeholder(name, prop)
            )
        return out

    return fill(schema)


# Where a placeholder would break one of the tool's own rules. Each still aims at
# nothing that exists.
OVERRIDES: dict[str, dict[str, Any]] = {
    "refunds_create": {"charge": f"ch_{MISSING}"},
    "checkout_sessions_create": {
        "mode": "payment",
        "line_items": [{"price": f"price_{MISSING}", "quantity": 1}],
        "success_url": "https://example.com/charter-scope-probe",
    },
}


def _offered(tool: Tool) -> set[str]:
    return {
        o
        for r in tool.kind_scopes[stripe.RESTRICTED_KEY]
        for o in (r.options if isinstance(r, AnyOf) else (r,))
    }


async def main() -> int:
    key = os.environ.get("STRIPE_PERMISSION_PROBE_KEY", "")
    if not key.startswith("rk_test_"):
        sys.exit("STRIPE_PERMISSION_PROBE_KEY must be a test-mode restricted key (rk_test_...)")
    stripe.configure(credential_provider=StaticTokenProvider(key))
    rows, bad = [], 0
    async with httpx.AsyncClient(timeout=30) as http:
        for tool in stripe.TOOLS:
            try:
                await tool.ainvoke({**_args(tool), **OVERRIDES.get(tool.name, {})}, client=http)
            except ToolValidationError as exc:
                rows.append({"tool": tool.name, "probe": "refused locally", "note": str(exc)[:200]})
                print(f"PROBE {tool.name:36} refused locally: {str(exc)[:120]}")
                continue
            except InsufficientScope as exc:
                named = set(exc.needed)
            except CharterError as exc:
                rows.append({"tool": tool.name, "probe": "inconclusive", "note": str(exc)[:300]})
                print(f"--   {tool.name:36} inconclusive: {str(exc)[:140]}")
                continue
            else:
                sys.exit(f"stopping: {tool.name} succeeded; the key holds a permission")
            offered = _offered(tool)
            ok = bool(named) and named <= offered
            bad += not ok
            rows.append(
                {"tool": tool.name, "named": sorted(named), "offered": sorted(offered), "ok": ok}
            )
            print(
                f"{'ok  ' if ok else 'FAIL'} {tool.name:36} Stripe names {sorted(named)}  "
                f"tool offers {sorted(offered)}"
            )
    print(
        f"\n{sum(1 for r in rows if r.get('ok'))} agree, {bad} disagree, "
        f"{sum(1 for r in rows if 'probe' in r)} not probed"
    )
    LIVE.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(rows, indent=2))
    print(f"report: {REPORT}")
    return 1 if bad else 0


if __name__ == "__main__":
    # A key pasted with its quotes, or a newline, is refused by Stripe as malformed.
    os.environ["STRIPE_PERMISSION_PROBE_KEY"] = re.sub(
        r"\s|['\"]", "", os.environ.get("STRIPE_PERMISSION_PROBE_KEY", "")
    )
    sys.exit(asyncio.run(main()))
