#!/usr/bin/env python
"""Does every Linear tool declare the OAuth scopes Linear itself says the operation accepts?

Deliberately not a test: the suite is offline by rule. Linear refuses an operation a
token's scopes do not cover before running it, and names what would have been
accepted: ``Invalid scope: `write` or `comments:create` required``. So a grant
holding only ``read`` is enough to read the answer for every mutation, and it can
change nothing: every mutation it sends is refused, and each is aimed at an id
that does not exist besides. Every query has to succeed with it.

    uv run python scripts/live_oauth_check.py connect --provider linear   # once: a `read` grant
    uv run python scripts/live_linear_scopes_check.py

Uses the grant ``live_oauth_check.py`` keeps in ``$CHARTER_LIVE_DIR/linear.json``,
refreshes it (and stores the rotated one back), and refuses to run unless Linear
reports the token as ``read`` and nothing more. Reads ``LINEAR_CLIENT_SECRET`` from
the environment or the repo's ``.env``. Prints no token.
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

from charter import CharterError, Tool, ToolValidationError
from charter.auth import AnyOf, StaticTokenProvider
from charter.packs import linear

ROOT = Path(__file__).resolve().parent.parent
LIVE = Path(os.environ.get("CHARTER_LIVE_DIR", Path.home() / ".charter/live"))
GRANT = LIVE / "linear.json"
REPORT = LIVE / "linear-scopes-check.json"
MISSING = "00000000-0000-0000-0000-000000000000"
_REFUSAL = re.compile(r"Invalid scope:\s*(.+?)\s+required", re.I)
# Refusals that happen before Linear checks scopes, so they prove nothing about them.
_BEFORE_SCOPE = re.compile(
    r"GRAPHQL_VALIDATION|got invalid value|Variable \"\$|Cannot query field|Argument Validation|Unknown argument",
    re.I,
)
# A refusal about the data, which only an operation past the scope check can reach.
_PAST_SCOPE = re.compile(r"not found|does not exist|Entity not found|could not find", re.I)


def _env(name: str) -> str:
    if os.environ.get(name):
        return os.environ[name]
    for line in (ROOT / ".env").read_text().splitlines():
        key, _, value = line.partition("=")
        if key.strip() == name:
            return value.strip().strip("'\"")
    sys.exit(f"{name} is not set")


def _placeholder(name: str, schema: dict[str, Any]) -> Any:
    if "enum" in schema:
        return schema["enum"][0]
    kind = schema.get("type")
    idish = name.lower().endswith(("id", "ids"))
    if kind == "array":
        return [MISSING] if idish else ["charter-scope-probe"]
    if kind == "integer":
        return 1
    if kind == "number":
        return 1.0
    if kind == "boolean":
        return False
    if idish:
        return MISSING
    if "url" in name.lower():
        return "https://example.com/charter-scope-probe"
    if "date" in name.lower() or "at" == name.lower()[-2:]:
        return "2031-01-01"
    return "charter-scope-probe"


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


def _camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(part.title() for part in rest)


def _satisfy(args: dict[str, Any], tool: Tool, refusal: str) -> dict[str, Any] | None:
    """Arguments that meet a rule of the tool's own the placeholders broke, or None.

    Charter's validators name what they want: "needs at least one field to change",
    "Give one of issue_id, project_id, …", "Name the comment by `id`". The fix stays
    aimed at nothing: a field set to a probe string, or an id that does not exist.
    """
    variables = dict(args.get("variables", {}))
    target = dict(variables.get("input", {}))
    one_of = re.search(r"Give one of ([a-z_, ]+)", refusal)
    if one_of:
        target[_camel(one_of.group(1).split(",")[0].strip())] = MISSING
    elif "at least one field to change" in refusal:
        schema = tool.to_json_schema()["parameters"]
        defs = schema.get("$defs", {})
        node = schema["properties"]["variables"]
        for key in ("variables", "input"):
            while "$ref" in node:
                node = defs[node["$ref"].split("/")[-1]]
            if key == "input":
                break
            node = node["properties"]["input"]
        while "$ref" in node:
            node = defs[node["$ref"].split("/")[-1]]
        for name, prop in node.get("properties", {}).items():
            branch = next((a for a in prop.get("anyOf", [prop]) if a.get("type") != "null"), prop)
            if "enum" in branch:
                target[name] = branch["enum"][0]
            elif branch.get("type") == "boolean":
                target[name] = False
            elif branch.get("type") in ("number", "integer"):
                target[name] = 1
            elif branch.get("type") == "string":
                target[name] = MISSING if name.lower().endswith("id") else "charter-scope-probe"
            else:
                continue
            break
    elif "by `id`" in refusal:
        variables["id"] = MISSING
        return {**args, "variables": variables}
    else:
        return None
    variables["input"] = target
    return {**args, "variables": variables}


def _options(requirement) -> tuple[str, ...]:
    return requirement.options if isinstance(requirement, AnyOf) else (requirement,)


async def _read_token(http: httpx.AsyncClient) -> str:
    grant = json.loads(GRANT.read_text())
    r = await http.post(
        "https://api.linear.app/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": grant["refresh_token"],
            "client_id": grant["client_id"],
            "client_secret": _env("LINEAR_CLIENT_SECRET"),
        },
    )
    if r.status_code != 200:
        sys.exit(
            f"refresh refused ({r.status_code}); run live_oauth_check.py connect --provider linear"
        )
    body = r.json()
    grant.update(
        access_token=body["access_token"],
        refresh_token=body.get("refresh_token", grant["refresh_token"]),
    )
    GRANT.write_text(json.dumps(grant))
    GRANT.chmod(0o600)
    scopes = {s.strip() for s in re.split(r"[ ,]", body.get("scope", "")) if s.strip()}
    if scopes != {"read"}:
        sys.exit(
            f"refusing: the grant holds {sorted(scopes)}; this check needs `read` and nothing more"
        )
    return body["access_token"]


async def main() -> int:
    rows, bad = [], 0
    async with httpx.AsyncClient(timeout=60) as http:
        linear.configure(credential_provider=StaticTokenProvider(await _read_token(http)))
        print("grant holds `read` and nothing more")
        for tool in linear.TOOLS:
            offered = {o for r in tool.scopes for o in _options(r)}
            args = _args(tool)
            try:
                try:
                    await tool.ainvoke(args, client=http)
                except ToolValidationError as first:
                    fixed = _satisfy(args, tool, str(first))
                    if fixed is None:
                        raise
                    await tool.ainvoke(fixed, client=http)
                answer, accepted = "ran", {"read"}
            except ToolValidationError as exc:
                rows.append({"tool": tool.name, "probe": "refused locally", "note": str(exc)[:200]})
                print(f"PROBE {tool.name:36} refused locally: {str(exc)[:120]}")
                continue
            except CharterError as exc:
                text = str(exc)
                match = _REFUSAL.search(text)
                if match:
                    answer = "refused for scope"
                    accepted = set(re.findall(r"`([^`]+)`", match.group(1)))
                elif _PAST_SCOPE.search(text) and not _BEFORE_SCOPE.search(text):
                    # Refused for an id that does not exist: the scope check passed,
                    # so `read` was enough.
                    answer, accepted = "ran past the scope check", {"read"}
                else:
                    rows.append({"tool": tool.name, "probe": "inconclusive", "note": text[:300]})
                    print(f"--   {tool.name:36} inconclusive: {text[:140]}")
                    continue
            # The tool must offer only scopes Linear accepts, and at least one.
            ok = bool(offered) and offered <= accepted
            bad += not ok
            rows.append(
                {
                    "tool": tool.name,
                    "answer": answer,
                    "accepted": sorted(accepted),
                    "offered": sorted(offered),
                    "ok": ok,
                }
            )
            mark = "ok  " if ok else "FAIL"
            print(
                f"{mark} {tool.name:36} {answer:26} Linear accepts {sorted(accepted)}  "
                f"tool offers {sorted(offered)}"
            )
    print(
        f"\n{sum(1 for r in rows if r.get('ok'))} agree, {bad} disagree, "
        f"{sum(1 for r in rows if 'probe' in r)} not probed"
    )
    REPORT.write_text(json.dumps(rows, indent=2))
    print(f"report: {REPORT}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
