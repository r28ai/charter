# Demo assets

Two phases, pip-only. `ffmpeg` is the single system dependency, and **no
credentials are needed** — every beat is public Charter API against local
state, so anyone who can `pip install charter-ai` can reproduce the asset.

```bash
./demo/record.sh
```

**Phase 1 — `capture.py`** runs the beats under the project venv and writes
`transcript.json`. Every output string in that file is what the interpreter
actually returned. If the API changes, the numbers in the demo change with it,
and a renamed symbol breaks the capture rather than silently going stale.

**Phase 2 — `render.py`** reads the transcript under `demo/.venv` (pillow +
pygments) and draws a Python REPL on pure black, with per-token highlighting
taken from VS Code's Default High Contrast (`hc_black`) theme — parsed from the
app bundle, not eyeballed. Encodes to `docs/images/<stem>.gif` and `.mp4`.

Neither is committed — both are in `.gitignore`. The video is hosted on GitHub's
user-attachments CDN so that no binary enters this repository's history, and the
README points at that URL. What *is* committed is a single still, the fallback
PyPI shows because its sanitiser strips `<video>` and keeps the inner `<img>`.
Re-render and the still goes stale with the video, so regenerate it too:

```bash
ffmpeg -i docs/images/charter-demo.mp4 -vf "select=eq(n\,339)" \
       -frames:v 1 -c:v libwebp -quality 75 docs/images/charter-demo-still.webp
```

Frame 339 is the one that carries the whole argument in one image: the
declaration, the three fields going in, the wire, and the `200 OK`. If the beats
move, pick the new frame rather than trusting that number.

## The beats

| beat | what lands on screen |
|---|---|
| 1 | `class SendMessage` + `oauth_tool_factory` → the whole tool, declared |
| 2 | `await send.ainvoke({...})` → the POST, the bearer, the base64 Charter built, the RFC 2822 document underneath it, and Gmail's `200 OK` |
| 3 | `schema_tokens(linear.issues_list_full)` → 45,072 tokens for one tool |
| 4 | `format_path_costs(paths(by_cost=True))` → one field of five is ~99% of it |
| 5 | `derived(keep={...})` → 2,267 tokens, the same job |
| 6 | `pin` + `format_egress_map` → the boundary, printed |

Everything typed on screen is documented public API. The four wire lines in beat
2 are the exception and the point: `capture.py` wraps `httpx.AsyncClient.send`
to print the request Charter assembled. That hook is instrumentation, not
something a reader would write — it is there because the argument of the beat is
what the runtime put on the wire from the declaration above it, and no public
API prints that.

## Editing it

Beats live in `BEATS` in `capture.py` as `(source, hold_seconds)` pairs.
`"__clear__"` wipes the screen. Long output lines wrap rather than clip.

Look and pacing are constants at the top of `render.py`: `FPS`, `SS`
(supersampling), `W`/`H`, `CPF_CODE`/`CPF_TEXT`, and the palette. Rendering at
`SS = 2` takes a few minutes; set `SS = 1` for fast drafts.

Pygments tags bare identifiers as `Name` regardless of role, so two heuristics
in `highlight()` recover what an editor shows: CamelCase reads as a type, a
name before `(` reads as a call.

## Why this lives in the repo

`demo/` ships in neither artifact — the sdist allowlist in `pyproject.toml`
covers `/src`, `/tests`, `/examples` and the metadata files, and the wheel
carries only `charter/`. It is here because the asset asserts facts about this
package, and an asset generator in another repo cannot break when those facts
change.
