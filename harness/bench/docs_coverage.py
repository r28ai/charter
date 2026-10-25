"""Google Docs through Charter and through Composio: what each can reach, and how.

No model, no document. Two questions, from the tool definitions each option hands
a model, read on the day:

- **Coverage.** Google's ``documents.batchUpdate`` takes 53 kinds of edit (the
  ``Request`` schema in the Docs v1 discovery document). For each kind: does an
  option offer it as a typed tool, whose schema names its fields, or only through
  an untyped passthrough, where the model writes the request from memory, or not
  at all?
- **Traceability.** Of every field name an option's Docs tools declare, at any
  depth, the share that is a field or parameter name somewhere in Google's Docs
  API, once spelled in camelCase. Lenient on purpose: a name only has to exist
  somewhere in the API, not in the right place.

Composio's tools are listed from its API (``toolkit_slug=googledocs``), Charter's
from the ``gdocs`` pack. Tools that are not Docs operations (Composio's Sheets
charts, its Drive search and copy) are left out and named.

    cd harness && CHARTER_HARNESS_ENV=... .venv/bin/python bench/docs_coverage.py

Writes ``results/bench/docs_coverage.json`` and ``results/bench/docs_coverage.md``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import httpx
from pydantic.alias_generators import to_camel

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "same_calls"))
from charter.packs import gdocs  # noqa: E402
from servers import _env  # noqa: E402

OUT = HERE.parent / "results" / "bench"
DISCOVERY = "https://docs.googleapis.com/$discovery/rest?version=v1"
COMPOSIO = "https://backend.composio.dev/api/v3/tools"

# Composio's typed tools, by the batchUpdate kind each one sends. Read off each
# tool's description and schema; DELETE_TABLE deletes a table's content range.
COMPOSIO_KINDS = {
    "GOOGLEDOCS_CREATE_FOOTER": "createFooter",
    "GOOGLEDOCS_CREATE_FOOTNOTE": "createFootnote",
    "GOOGLEDOCS_CREATE_HEADER": "createHeader",
    "GOOGLEDOCS_CREATE_NAMED_RANGE": "createNamedRange",
    "GOOGLEDOCS_CREATE_PARAGRAPH_BULLETS": "createParagraphBullets",
    "GOOGLEDOCS_DELETE_CONTENT_RANGE": "deleteContentRange",
    "GOOGLEDOCS_DELETE_TABLE": "deleteContentRange",
    "GOOGLEDOCS_DELETE_FOOTER": "deleteFooter",
    "GOOGLEDOCS_DELETE_HEADER": "deleteHeader",
    "GOOGLEDOCS_DELETE_NAMED_RANGE": "deleteNamedRange",
    "GOOGLEDOCS_DELETE_PARAGRAPH_BULLETS": "deleteParagraphBullets",
    "GOOGLEDOCS_DELETE_TABLE_COLUMN": "deleteTableColumn",
    "GOOGLEDOCS_DELETE_TABLE_ROW": "deleteTableRow",
    "GOOGLEDOCS_INSERT_INLINE_IMAGE": "insertInlineImage",
    "GOOGLEDOCS_INSERT_PAGE_BREAK": "insertPageBreak",
    "GOOGLEDOCS_INSERT_TABLE_ACTION": "insertTable",
    "GOOGLEDOCS_INSERT_TABLE_COLUMN": "insertTableColumn",
    "GOOGLEDOCS_INSERT_TEXT_ACTION": "insertText",
    "GOOGLEDOCS_REPLACE_ALL_TEXT": "replaceAllText",
    "GOOGLEDOCS_REPLACE_IMAGE": "replaceImage",
    "GOOGLEDOCS_UNMERGE_TABLE_CELLS": "unmergeTableCells",
    "GOOGLEDOCS_UPDATE_DOCUMENT_STYLE": "updateDocumentStyle",
    "GOOGLEDOCS_UPDATE_TABLE_ROW_STYLE": "updateTableRowStyle",
}
COMPOSIO_PASSTHROUGH = "GOOGLEDOCS_UPDATE_EXISTING_DOCUMENT"  # editDocs: list of untyped objects
NOT_DOCS = {
    "GOOGLEDOCS_GET_CHARTS_FROM_SPREADSHEET": "reads a Sheets spreadsheet",
    "GOOGLEDOCS_LIST_SPREADSHEET_CHARTS_ACTION": "reads a Sheets spreadsheet",
    "GOOGLEDOCS_SEARCH_DOCUMENTS": "searches Drive",
    "GOOGLEDOCS_COPY_DOCUMENT": "copies through Drive",
}


def field_names(schema: dict[str, Any], defs: dict[str, Any] | None = None) -> list[str]:
    """Every property name in a JSON schema, at any depth, following ``$ref`` once each."""
    defs = schema.get("$defs", defs or {})
    seen: set[str] = set()
    out: list[str] = []

    def walk(s: Any) -> None:
        if not isinstance(s, dict):
            return
        ref = s.get("$ref")
        if ref:
            name = ref.split("/")[-1]
            if name in seen:
                return
            seen.add(name)
            walk(defs.get(name, {}))
            return
        for k, v in (s.get("properties") or {}).items():
            out.append(k)
            walk(v)
        for key in ("items", "additionalProperties"):
            walk(s.get(key))
        for key in ("anyOf", "oneOf", "allOf"):
            for sub in s.get(key) or []:
                walk(sub)

    walk(schema)
    return out


def google_names(discovery: dict[str, Any]) -> set[str]:
    names = {k for s in discovery["schemas"].values() for k in (s.get("properties") or {})}
    for method in discovery["resources"]["documents"]["methods"].values():
        names |= set(method.get("parameters") or {})
    return names


def main() -> None:
    discovery = httpx.get(DISCOVERY, timeout=30).json()
    kinds = list(discovery["schemas"]["Request"]["properties"])
    known = google_names(discovery)
    composio = httpx.get(
        COMPOSIO,
        params={"toolkit_slug": "googledocs", "limit": 200},
        headers={"x-api-key": _env("COMPOSIO_API_KEY")},
        timeout=30,
    ).json()["items"]

    charter_batch = next(t for t in gdocs.TOOLS if t.name == "documents_batch_update")
    batch_schema = charter_batch.to_json_schema()["parameters"]
    charter_kinds = set(batch_schema["$defs"]["Request_LLM"]["properties"])
    composio_typed = {COMPOSIO_KINDS[t["slug"]] for t in composio if t["slug"] in COMPOSIO_KINDS}
    has_passthrough = any(t["slug"] == COMPOSIO_PASSTHROUGH for t in composio)

    per_kind = []
    for kind in kinds:
        per_kind.append(
            {
                "kind": kind,
                "charter": "typed" if kind in charter_kinds else "not reachable",
                "composio": "typed"
                if kind in composio_typed
                else ("untyped passthrough" if has_passthrough else "not reachable"),
            }
        )

    def trace(tools: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
        names = [n for _, schema in tools for n in field_names(schema)]
        mapped = [n for n in names if to_camel(n) in known or n in known]
        unmapped = sorted({n for n in names if n not in mapped})
        return {"fields": len(names), "traceable": len(mapped), "unmapped": unmapped}

    composio_docs = [t for t in composio if t["slug"] not in NOT_DOCS]
    result = {
        "kinds": len(kinds),
        "per_kind": per_kind,
        "charter": {
            "tools": len(gdocs.TOOLS),
            "typed_kinds": len(charter_kinds & set(kinds)),
            "trace": trace([(t.name, t.to_json_schema()["parameters"]) for t in gdocs.TOOLS]),
        },
        "composio": {
            "tools": len(composio),
            "docs_tools": len(composio_docs),
            "not_docs": {t["slug"]: NOT_DOCS[t["slug"]] for t in composio if t["slug"] in NOT_DOCS},
            "typed_kinds": len(composio_typed & set(kinds)),
            "passthrough": COMPOSIO_PASSTHROUGH if has_passthrough else None,
            "trace": trace([(t["slug"], t["input_parameters"]) for t in composio_docs]),
            "unmapped_tools": sorted(
                t["slug"]
                for t in composio
                if t["slug"] not in COMPOSIO_KINDS and t["slug"] not in NOT_DOCS
            ),
        },
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "docs_coverage.json").write_text(json.dumps(result, indent=2))
    c, k = result["charter"], result["composio"]
    neither = [r["kind"] for r in per_kind if r["charter"] != "typed" and r["composio"] != "typed"]
    lines = [
        f"Google's `documents.batchUpdate` takes {len(kinds)} kinds of edit.",
        "",
        "| | Charter (`gdocs`) | Composio (`googledocs`) |",
        "|---|---:|---:|",
        f"| Docs tools | {c['tools']} | {k['docs_tools']} (of {k['tools']} listed) |",
        f"| kinds of edit with a typed schema | {c['typed_kinds']} | {k['typed_kinds']} |",
        f"| kinds reachable only untyped | 0 | {len(kinds) - k['typed_kinds'] if k['passthrough'] else 0} |",
        f"| kinds not reachable | {len(kinds) - c['typed_kinds']} | "
        f"{0 if k['passthrough'] else len(kinds) - k['typed_kinds']} |",
        f"| tool fields that are a name in Google's Docs API | {c['trace']['traceable']}/{c['trace']['fields']} | "
        f"{k['trace']['traceable']}/{k['trace']['fields']} |",
        "",
        f"Typed by neither ({len(neither)}): " + ", ".join(f"`{n}`" for n in neither),
        "",
        "Composio fields that are no name in Google's Docs API: "
        + ", ".join(f"`{n}`" for n in k["trace"]["unmapped"]),
        "",
        "Charter fields that are no name in Google's Docs API: "
        + (", ".join(f"`{n}`" for n in c["trace"]["unmapped"]) or "none"),
        "",
        "Composio tools left out as not Docs operations: "
        + ", ".join(f"`{s}` ({why})" for s, why in k["not_docs"].items()),
    ]
    text = "\n".join(lines) + "\n"
    (OUT / "docs_coverage.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
