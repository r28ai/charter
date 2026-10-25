"""One small edit to a Google Doc, three ways: what does each leave of the document?

No model. One document is built with what an edit can destroy: a heading in a named
style, a coloured run, a bold run, a link, a footnote, a named range, a bulleted
list and a table. Three copies are made, and in each "12%" becomes "14%":

- ``charter``: ``gdocs.documents_batch_update`` with one ``replaceAllText``.
- ``composio_typed``: Composio's ``GOOGLEDOCS_REPLACE_ALL_TEXT``.
- ``composio_markdown``: Composio's ``GOOGLEDOCS_UPDATE_DOCUMENT_MARKDOWN``, with the
  document written as Markdown carrying the change, which is what an agent using
  that tool has to send. Markdown has no colour, footnote or named range in Google's
  sense, so the Markdown below carries what it can: the heading levels, the bold,
  the link, the list, the table, and a footnote in the common ``[^1]`` syntax.

Each copy is read back through Google's own API on the account that made it and
checked element by element against what was built. Composio's copies are link-
shared for the minutes the test runs, because its connected Google account is a
different test account; the share is removed and every copy is deleted at the end.
Comments and suggestions are not tested: the API cannot create a suggestion, and a
comment it creates is not anchored to text.

    cd harness && CHARTER_HARNESS_ENV=... .venv/bin/python bench/docs_edit_loss.py

Writes ``results/bench/docs_edit_loss.json`` and ``results/bench/docs_edit_loss.md``.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import httpx

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "same_calls"))
from charter.packs import gdocs  # noqa: E402
from servers import _env  # noqa: E402

OUT = HERE.parent / "results" / "bench"
DOCS = "https://docs.googleapis.com/v1/documents"
DRIVE = "https://www.googleapis.com/drive/v3/files"
COMPOSIO = "https://backend.composio.dev/api/v3/tools/execute"
COMPOSIO_DOCS_ACCOUNT = "COMPOSIO_DOCS_ACCOUNT"  # harness .env: the googledocs connection

TITLE = "Quarterly review"
LINES = [
    TITLE,
    "Revenue grew 12% this quarter, led by renewals.",
    "Next steps",
    "Ship the new pricing page",
    "Hire two engineers",
]
FOOTNOTE = "Renewals include multi-year contracts."
TABLE = [["Metric", "Value"], ["ARR", "$1.2M"]]
LINK = "https://example.com/renewals"
NAMED_RANGE = "headline"
MARKDOWN = f"""# {TITLE}

Revenue grew **14%** this quarter, led by [renewals]({LINK})[^1].

## Next steps

- Ship the new pricing page
- Hire two engineers

| Metric | Value |
|---|---|
| ARR | $1.2M |

[^1]: {FOOTNOTE}
"""


# -----------------------------------------------------------------------------
# Building the document
# -----------------------------------------------------------------------------


def _find(doc: dict[str, Any], needle: str) -> int:
    """The document index where ``needle`` starts, in the body."""
    for el in doc["body"]["content"]:
        for run in (el.get("paragraph") or {}).get("elements", []):
            text = (run.get("textRun") or {}).get("content", "")
            at = text.find(needle)
            if at >= 0:
                return run["startIndex"] + at
    raise LookupError(needle)


async def build(http: httpx.AsyncClient, h: dict[str, str], name: str) -> str:
    doc = (await http.post(DOCS, headers=h, json={"title": f"[charter-bench] {name}"})).json()
    did = doc["documentId"]

    async def batch(requests: list[dict[str, Any]]) -> None:
        r = await http.post(f"{DOCS}/{did}:batchUpdate", headers=h, json={"requests": requests})
        r.raise_for_status()

    async def get() -> dict[str, Any]:
        return (await http.get(f"{DOCS}/{did}", headers=h)).json()

    await batch([{"insertText": {"location": {"index": 1}, "text": "\n".join(LINES) + "\n"}}])
    d = await get()
    line = {t: _find(d, t) for t in LINES}
    rev = _find(d, "12%")
    led = _find(d, "led by")
    ren = _find(d, "renewals")
    await batch(
        [
            {
                "updateParagraphStyle": {
                    "range": {"startIndex": line[TITLE], "endIndex": line[TITLE] + len(TITLE)},
                    "paragraphStyle": {"namedStyleType": "HEADING_1"},
                    "fields": "namedStyleType",
                }
            },
            {
                "updateParagraphStyle": {
                    "range": {
                        "startIndex": line["Next steps"],
                        "endIndex": line["Next steps"] + 10,
                    },
                    "paragraphStyle": {"namedStyleType": "HEADING_2"},
                    "fields": "namedStyleType",
                }
            },
            {
                "updateTextStyle": {
                    "range": {"startIndex": rev, "endIndex": rev + 3},
                    "textStyle": {"bold": True},
                    "fields": "bold",
                }
            },
            {
                "updateTextStyle": {
                    "range": {"startIndex": led, "endIndex": led + 6},
                    "textStyle": {
                        "foregroundColor": {
                            "color": {"rgbColor": {"red": 0.8, "green": 0.1, "blue": 0.1}}
                        }
                    },
                    "fields": "foregroundColor",
                }
            },
            {
                "updateTextStyle": {
                    "range": {"startIndex": ren, "endIndex": ren + 8},
                    "textStyle": {"link": {"url": LINK}},
                    "fields": "link",
                }
            },
            {
                "createParagraphBullets": {
                    "range": {
                        "startIndex": line["Ship the new pricing page"],
                        "endIndex": line["Hire two engineers"] + len("Hire two engineers"),
                    },
                    "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE",
                }
            },
            {
                "createNamedRange": {
                    "name": NAMED_RANGE,
                    "range": {
                        "startIndex": line[LINES[1]],
                        "endIndex": line[LINES[1]] + len(LINES[1]),
                    },
                }
            },
        ]
    )
    # The footnote after "renewals", then its text.
    d = await get()
    ren = _find(d, "renewals")
    await batch([{"createFootnote": {"location": {"index": ren + len("renewals")}}}])
    d = await get()
    fid, footnote = next(iter(d["footnotes"].items()))
    # A new footnote holds " \n" from index 0 (which Google omits); text goes after the space.
    start = footnote["content"][0].get("startIndex", 0) + 1
    await batch(
        [{"insertText": {"location": {"segmentId": fid, "index": start}, "text": FOOTNOTE}}]
    )
    # A 2x2 table at the end, filled from the last cell back so indexes hold.
    d = await get()
    end = d["body"]["content"][-1]["endIndex"] - 1
    await batch([{"insertTable": {"rows": 2, "columns": 2, "location": {"index": end}}}])
    d = await get()
    table = next(el for el in d["body"]["content"] if "table" in el)
    cells = [
        (r, c, cell["content"][0]["startIndex"])
        for r, row in enumerate(table["table"]["tableRows"])
        for c, cell in enumerate(row["tableCells"])
    ]
    await batch(
        [
            {"insertText": {"location": {"index": idx}, "text": TABLE[r][c]}}
            for r, c, idx in sorted(cells, key=lambda x: -x[2])
        ]
    )
    return did


# -----------------------------------------------------------------------------
# Reading it back
# -----------------------------------------------------------------------------


def _runs(doc: dict[str, Any]):
    for el in doc["body"]["content"]:
        p = el.get("paragraph")
        if p:
            for run in p.get("elements", []):
                if "textRun" in run:
                    yield p, run["textRun"]


def check(doc: dict[str, Any], value: str = "14%") -> dict[str, bool]:
    """Each element, against the document as built; ``value`` is the edited figure."""
    other = "12%" if value == "14%" else "14%"
    text = "".join(t["content"] for _, t in _runs(doc))
    styles = {
        "".join(r.get("textRun", {}).get("content", "") for r in p.get("elements", [])).strip(): p[
            "paragraphStyle"
        ].get("namedStyleType")
        for el in doc["body"]["content"]
        if (p := el.get("paragraph"))
    }
    runs = [t for _, t in _runs(doc)]

    def styled(needle: str, test) -> bool:
        return any(needle in t["content"] and test(t.get("textStyle", {})) for t in runs)

    lists = [p for el in doc["body"]["content"] if (p := el.get("paragraph")) and p.get("bullet")]
    tables = [el["table"] for el in doc["body"]["content"] if "table" in el]
    cell_text = []
    for t in tables:
        for row in t["tableRows"]:
            cell_text.append(
                [
                    "".join(
                        r.get("textRun", {}).get("content", "")
                        for c in cell["content"]
                        for r in c.get("paragraph", {}).get("elements", [])
                    ).strip()
                    for cell in row["tableCells"]
                ]
            )
    footnotes = doc.get("footnotes") or {}
    footnote_text = " ".join(
        r.get("textRun", {}).get("content", "")
        for f in footnotes.values()
        for c in f["content"]
        for r in c.get("paragraph", {}).get("elements", [])
    )

    def color(style: dict[str, Any]) -> bool:
        return bool(
            style.get("foregroundColor", {}).get("color", {}).get("rgbColor", {}).get("red")
        )

    return {
        "the figure": value in text and other not in text,
        "the rest of the text": all(line.replace("12%", value) in text for line in LINES),
        "heading 1 (named style)": styles.get(TITLE) == "HEADING_1",
        "heading 2 (named style)": styles.get("Next steps") == "HEADING_2",
        "bold": styled(value, lambda s: s.get("bold")),
        "coloured text": styled("led by", color),
        "link": styled("renewals", lambda s: s.get("link", {}).get("url") == LINK),
        "bulleted list": len(lists) == 2,
        "table": len(tables) == 1 and cell_text == TABLE,
        "footnote": len(footnotes) == 1 and FOOTNOTE in footnote_text,
        "named range": NAMED_RANGE in (doc.get("namedRanges") or {}),
    }


# -----------------------------------------------------------------------------
# The three edits
# -----------------------------------------------------------------------------


async def composio(http: httpx.AsyncClient, slug: str, arguments: dict[str, Any]) -> dict[str, Any]:
    r = await http.post(
        f"{COMPOSIO}/{slug}",
        headers={"x-api-key": _env("COMPOSIO_API_KEY")},
        json={
            "connected_account_id": _env(COMPOSIO_DOCS_ACCOUNT),
            "user_id": "charter-benchmark",
            "arguments": arguments,
            "version": "latest",
        },
        timeout=120,
    )
    return r.json()


async def main() -> None:
    from charter_harness.settings import load, wire_packs

    wiring = wire_packs(load(), frozenset({"gdocs", "gdrive"}))
    h = {"Authorization": f"Bearer {await wiring.google_token()}"}
    made: list[str] = []
    results: dict[str, Any] = {}
    async with httpx.AsyncClient(timeout=60) as http:
        try:
            reference = await build(http, h, "edit-loss reference")
            made.append(reference)
            results["built"] = check(
                (await http.get(f"{DOCS}/{reference}", headers=h)).json(), value="12%"
            )
            for path in ("charter", "composio_typed", "composio_markdown"):
                did = await build(http, h, f"edit-loss {path}")
                made.append(did)
                if path == "charter":
                    await gdocs.documents_batch_update.ainvoke(
                        {
                            "documentId": did,
                            "body": {
                                "requests": [
                                    {
                                        "replaceAllText": {
                                            "containsText": {"text": "12%", "matchCase": True},
                                            "replaceText": "14%",
                                        }
                                    }
                                ]
                            },
                        },
                        client=http,
                    )
                    reply = "ok"
                else:
                    share = await http.post(
                        f"{DRIVE}/{did}/permissions",
                        headers=h,
                        json={"type": "anyone", "role": "writer"},
                    )
                    share.raise_for_status()
                    if path == "composio_typed":
                        out = await composio(
                            http,
                            "GOOGLEDOCS_REPLACE_ALL_TEXT",
                            {
                                "document_id": did,
                                "find_text": "12%",
                                "replace_text": "14%",
                                "match_case": True,
                            },
                        )
                    else:
                        out = await composio(
                            http,
                            "GOOGLEDOCS_UPDATE_DOCUMENT_MARKDOWN",
                            {"document_id": did, "new_markdown_text": MARKDOWN},
                        )
                    reply = {"successful": out.get("successful"), "error": out.get("error")}
                    await http.delete(f"{DRIVE}/{did}/permissions/anyoneWithLink", headers=h)
                doc = (await http.get(f"{DOCS}/{did}", headers=h)).json()
                results[path] = {
                    "reply": reply,
                    "kept": check(doc),
                    # What is there now, so a "lost" can be read back.
                    "text": "".join(t["content"] for _, t in _runs(doc)),
                    "bullets": sum(
                        1
                        for el in doc["body"]["content"]
                        if (el.get("paragraph") or {}).get("bullet")
                    ),
                    "footnotes": len(doc.get("footnotes") or {}),
                    "named_ranges": sorted(doc.get("namedRanges") or {}),
                }
                print(path, json.dumps(results[path]))
        finally:
            for did in made:
                await http.delete(f"{DRIVE}/{did}", headers=h)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "docs_edit_loss.json").write_text(json.dumps(results, indent=2))
    elements = list(results["built"])
    lines = [
        "| what the document held | Charter (`replaceAllText`) | Composio `REPLACE_ALL_TEXT` | Composio `UPDATE_DOCUMENT_MARKDOWN` |",
        "|---|---|---|---|",
    ]
    mark = {True: "kept", False: "**lost**"}
    for e in elements:
        assert results["built"][e], f"the document was not built with {e}"
        lines.append(
            f"| {e} | "
            + " | ".join(
                mark[results[p]["kept"][e]]
                for p in ("charter", "composio_typed", "composio_markdown")
            )
            + " |"
        )
    text = "\n".join(lines) + "\n"
    (OUT / "docs_edit_loss.md").write_text(text)
    print(text)


if __name__ == "__main__":
    asyncio.run(main())
