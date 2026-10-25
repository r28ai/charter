"""The same-calls table, read off ``results/bench/same_calls.jsonl``: the latest row per case and layer."""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent.parent / "results" / "bench"
KINDS = {
    "failure": "A failure the API reports inside a 2xx",
    "contract": "A call outside the documented contract",
    "wire": "A Gmail draft, read back through Gmail's API",
}


def main() -> None:
    latest: dict[tuple[str, str], dict] = {}
    for line in (OUT / "same_calls.jsonl").read_text().splitlines():
        row = json.loads(line)
        latest[(row["case"], row["layer"])] = row
    layers = ["charter", "mcp", "raw"]
    extra = sorted({layer for _, layer in latest} - set(layers))
    order = (
        layers[:1]
        + [x for x in extra if x.startswith("charter")]
        + layers[1:]
        + [x for x in extra if not x.startswith("charter")]
    )
    lines = []
    for kind, title in KINDS.items():
        cases = sorted({c for (c, _), r in latest.items() if r["kind"] == kind})
        if not cases:
            continue
        lines += [
            f"### {title}",
            "",
            "| case | " + " | ".join(order) + " | the vendor's words |",
            "|---|" + "---|" * (len(order) + 1),
        ]
        for case in cases:
            any_row = next(r for (c, _), r in latest.items() if c == case)
            cells = [latest.get((case, layer), {}).get("label", "") for layer in order]
            lines.append(f"| {case} | " + " | ".join(cells) + f" | {any_row['doc']} |")
        lines.append("")
    servers = sorted({r["server"] for r in latest.values() if r["layer"] == "mcp"})
    lines += ["MCP servers: " + "; ".join(servers) + "."]
    text = "\n".join(lines) + "\n"
    (OUT / "same_calls.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
