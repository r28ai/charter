"""Phase 2 — render demo/transcript.json to a GIF and an MP4.

One pane, the way a real session looks: a Python REPL on pure black, with
per-token syntax highlighting taken from VS Code's Default High Contrast
(hc_black) theme. No editor chrome, no labelled panes — the artifact is the
terminal, so it is drawn as a terminal.

Deterministic: same transcript in, same frames out.
"""
import json, pathlib, re, shutil, subprocess, sys, tempfile
from PIL import Image, ImageDraw, ImageFont
from pygments import lex
from pygments.lexers import PythonLexer
from pygments.token import Token

HERE = pathlib.Path(__file__).parent
FPS = 20
SS = 2                              # supersample: rasterise at 2x, downscale.
                                    # 1x leaves PIL's grey AA thin and washes
                                    # the hues out; 2x reads like a retina grab.
W, H = 1280, 1080
TITLEBAR, PAD = 38 * SS, 24 * SS
SIZE, LEADING = 22 * SS, 1.42
RW, RH = W * SS, H * SS
CPF_CODE, CPF_TEXT = 6, 3          # chars per frame: code types fast, prose reads

# VS Code "Default High Contrast" (hc_black), read from the app bundle.
BG, CHROME, FG = "#000000", "#0b0b0c", "#ffffff"
COMMENT, KEYWORD, CONTROL = "#7ca668", "#569cd6", "#c586c0"
STRING, NUMBER, TYPE = "#ce9178", "#b5cea8", "#4ec9b0"
FUNC, VARIABLE, DIM = "#dcdcaa", "#9cdcfe", "#6e7681"
CAPTION = "#98c379"          # green: the brain files it as a comment
DOTS = ["#ff5f57", "#febc2e", "#28c840"]

TOKEN_COLOURS = [
    (Token.Comment, COMMENT),
    (Token.Keyword.Namespace, CONTROL), (Token.Operator.Word, CONTROL),
    (Token.Keyword.Constant, KEYWORD), (Token.Keyword, CONTROL),
    (Token.Name.Builtin.Pseudo, KEYWORD), (Token.Name.Builtin, FUNC),
    (Token.Name.Class, TYPE), (Token.Name.Function, FUNC),
    (Token.String.Escape, NUMBER), (Token.String, STRING),
    (Token.Number, NUMBER),
    (Token.Operator, FG), (Token.Punctuation, FG),
    (Token.Name, VARIABLE),
]
CAMEL = re.compile(r"^[A-Z][A-Za-z0-9]*$")

def font():
    for p in ("/System/Library/Fonts/Menlo.ttc", "/System/Library/Fonts/SFNSMono.ttf"):
        try: return ImageFont.truetype(p, SIZE, index=0)
        except Exception: continue
    raise SystemExit("no monospace font found")

F = font()
CH_W = F.getlength("M")   # true advance; bbox under-measures and drifts
LINE_H = int(SIZE * LEADING)
ROWS = (RH - TITLEBAR - PAD * 2) // LINE_H
COLS = int((RW - PAD * 2) // CH_W)

def _mix(hex_colour, amount):
    """Blend a colour toward the background. amount=0 keeps it, 1 erases it."""
    h = hex_colour.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    br, bg_, bb = (int(BG.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    f = lambda c, base: int(round(c + (base - c) * amount))
    return f"#{f(r, br):02x}{f(g, bg_):02x}{f(b, bb):02x}"


def colour_for(tok):
    for prefix, col in TOKEN_COLOURS:
        if tok in prefix: return col
    return FG

def highlight(text):
    """[(text, colour)]. Two heuristics recover what an editor shows:
    CamelCase reads as a type, a name before "(" reads as a call."""
    runs = [[v, colour_for(t), t] for t, v in lex(text, PythonLexer()) if v]
    for i, (v, _, t) in enumerate(runs):
        if t not in Token.Name: continue
        if CAMEL.match(v): runs[i][1] = TYPE
        elif i + 1 < len(runs) and runs[i + 1][0].startswith("("): runs[i][1] = FUNC
    return [(v, c) for v, c, _ in runs]

def out_runs(line):
    """Output lines: numbers and structure pop, prose stays plain."""
    if re.fullmatch(r"\s*-?\d[\d,]*\s*", line): return [(line, NUMBER)]
    return [(line, FG)]

def wrap_runs(runs, cols):
    """Fold coloured runs to the window width, keeping colours intact."""
    lines, cur, used = [], [], 0
    for text, col in runs:
        while text:
            room = cols - used
            if len(text) <= room:
                cur.append((text, col)); used += len(text); text = ""
            else:
                cur.append((text[:room], col)); text = text[room:]
                lines.append(cur); cur, used = [("  ", col)], 2
    lines.append(cur)
    return lines

def annotated(rows, keep, caption):
    """Rows with the caption attached to the block it describes.

    Beside the anchor line when the line is short enough to leave room — that
    reads as an aside on the thing itself. Otherwise on its own line under the
    block, because overlapping a long URL is how the first version became
    invisible.
    """
    if not keep or not caption:
        return rows, keep
    first, last = min(keep), max(keep)
    head = "".join(t for t, _ in rows[first])
    if len(head) + 4 + len(caption) + 2 <= COLS:
        pad = " " * (len(head) + 4)
        out = list(rows)
        out[first] = rows[first] + [(pad[len(head):] + "\u2190 " + caption, CAPTION)]
        return out, keep
    indent = len(head) - len(head.lstrip())
    row = [(" " * indent + "\u2191 " + caption, CAPTION)]
    out = rows[:last + 1] + [row] + rows[last + 1:]
    return out, {i if i <= last else i + 1 for i in keep} | {last + 1}


def frame(rows, keep=None, amount=0.0, shift=0, label=None, label_row=None):
    img = Image.new("RGB", (RW, RH), CHROME)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, RW - 1, RH - 1], radius=11 * SS, fill=CHROME)
    for i, c in enumerate(DOTS):
        x0 = PAD + i * 22 * SS
        d.ellipse([x0, 14 * SS, x0 + 11 * SS, 25 * SS], fill=c)
    d.text((RW // 2, 19 * SS), "python3", font=F, fill=DIM, anchor="mm")
    d.rounded_rectangle([0, TITLEBAR, RW - 1, RH - 1], radius=11 * SS, fill=BG)
    y = TITLEBAR + PAD - shift
    shown = rows[-(ROWS + (1 if shift else 0)):] if not shift else rows
    offset = len(rows) - len(shown)
    for i, line in enumerate(shown):
        faded = amount > 0 and keep is not None and (i + offset) not in keep
        x = PAD
        for text, col in line:
            col = _mix(col, amount) if faded else col
            if text:
                d.text((x, y), text, font=F, fill=col,
                       stroke_width=1, stroke_fill=col)
                x += F.getlength(text)
        if label and label_row is not None and (i + offset) == label_row:
            d.text((RW - PAD, y), label, font=F, fill=DIM, anchor="ra")
        y += LINE_H
    return img.resize((W, H), Image.LANCZOS)

def focus_stages(rows, first):
    """What to light, in what order. [] leaves the block alone.

    A wire block tells a three-part story and reads badly all at once: the
    request that went out, the document the encoded body actually is, then the
    answer. Lighting them in turn is the narration, without a caption.
    """
    block = range(first, len(rows))
    text = {i: "".join(t for t, _ in rows[i]) for i in block}

    if any("\u21b3 decoded" in text[i] for i in block):
        request = {i for i in block
                   if text[i].startswith(("POST ", "GET ", "PUT ", "PATCH ", "DELETE "))
                   or text[i].startswith(("authorization:", "content-type:"))
                   or text[i].lstrip().startswith('{"raw"')}
        answer = {i for i in block
                  if text[i].startswith("HTTP/") or text[i].lstrip().startswith("{'")}
        decoded = {i for i in block
                   if i not in request and i not in answer and text[i].strip()}
        return [(request, "charter built and signed all of this"),
                (decoded, "the RFC 2822 document you never wrote"),
                (answer, "gmail's answer")]

    import re as _re
    body = [i for i in block if text[i].strip()]
    if body and all(_re.fullmatch(r"\S+\s+[\d,]+", text[i].strip()) for i in body):
        return [(set(body), "99% of the tool's context")]

    pinned = {i for i in block
              if "[pinned]" in text[i]
              or text[i].lstrip().startswith("pinned (")
              or text[i].lstrip().startswith("= ")}
    return [(pinned, "not in the schema. sent on every request")] if pinned else []


def build(transcript):
    frames, rows, last_state = [], [], None
    def hold(n): frames.extend([frame(rows)] * max(1, int(n)))

    for step in transcript:
        src, out, pause = step["in"], step["out"], step["hold"]
        hold_for = pause
        if src.startswith("__spotlight__"):
            spec = src[len("__spotlight__"):].strip()
            spec, _, caption = spec.partition("|")
            targets = spec.split()
            caption = caption.strip() or None

            def _is_point(text):
                t = text.strip()
                if targets:
                    return any(tok in text for tok in targets)
                return bool(t) and (t.isdigit() or t.startswith("['"))
            keep = {i for i, r in enumerate(rows)
                    if _is_point("".join(x for x, _ in r))}
            if keep:
                # The caption belongs to the highlight, not to the session: do
                # not write it back into rows, or it outlives the beat that
                # explains it. Ramp fast and spend the time lit instead.
                rows_v, keep = annotated(rows, keep, caption)
                for step in range(1, 4):
                    frames.append(frame(rows_v, keep, 0.45 * step / 3))
                frames.extend([frame(rows_v, keep, 0.45)]
                              * max(1, int(FPS * ((hold_for or 3.0) - 0.15))))
                last_state = (rows_v, keep)
            continue
        if src == "__clear__":
            if last_state:                     # leave on the lit frame
                view, lit = last_state
                frames.extend([frame(view, lit, 0.45)] * int(FPS * 0.25))
            else:
                hold(FPS * 0.3)
            rows.clear(); last_state = None; continue
        if src == "__scroll__":
            # A terminal never gets its whitespace back, but a viewer needs it.
            # Slide rather than cut: the session has to stay continuous, and a
            # jump reads as an edit.
            hold(FPS * 0.3)
            tail = [r for r in rows if any(t.strip() for t, _ in r)][-6:]
            dropped = max(0, len(rows) - len(tail))
            if dropped:
                for step in range(1, 5):               # ~0.2s glide
                    frames.append(frame(rows, shift=int(dropped * LINE_H * step / 4)))
            rows.clear(); rows.extend(tail); rows.append([])
            hold(FPS * 0.2)
            continue
        if not src.strip():
            rows.append([]); hold(FPS * 0.2); continue

        is_text = src.lstrip().startswith("#")
        # Imports are throat-clearing. Nobody needs to watch "from typing
        # import Annotated" arrive a character at a time — land them whole.
        is_import = src.lstrip().startswith(("import ", "from "))
        # A class body is not an argument list. The markers on those fields are
        # what the demo is about, so they get typed out like a first line.
        is_decl = src.lstrip().startswith("class ")
        cpf = CPF_TEXT if is_text else CPF_CODE
        for li, sl in enumerate(src.splitlines()):
            prompt = [(">>> " if li == 0 else "... ", DIM)]
            rows.append(list(prompt))
            # A "... " row is an argument to a call whose name was read
            # on the line above. Typing it out is the same throat-clearing
            # as an import: land the rest of the statement whole.
            if is_import or (li and not is_decl):
                rows[-1] = prompt + highlight(sl)
                frames.append(frame(rows))
                continue
            for i in range(0, len(sl) + 1, cpf):
                rows[-1] = prompt + highlight(sl[:i])
                frames.append(frame(rows))
            rows[-1] = prompt + highlight(sl)
        hold(FPS * (0.12 if is_import else 0.3))

        last_state = None
        if out:
            # A big artifact lands better after a beat of dead air: the request
            # really is in flight, and the eye needs a moment to leave the line
            # it just read. A one-line answer needs no such ceremony.
            if len(out.splitlines()) >= 4:
                hold(FPS * 0.5)
            first = len(rows)
            for ol in out.splitlines():
                rows.extend(wrap_runs(out_runs(ol), COLS))

            # A long artifact answers one question. Read it whole first, then
            # dim what is not the answer — subtraction, rather than a marker
            # no terminal has.
            stages = focus_stages(rows, first)
            if stages and len(rows) - first >= 3:
                lead = 1.0
                hold(FPS * lead)
                each = max(1.0, (pause - lead) / len(stages))
                for keep, caption in stages:
                    view, lit = annotated(rows, keep, caption)
                    for step in range(1, 7):           # ~0.3s ramp
                        frames.append(frame(view, lit, 0.45 * step / 6))
                    frames.extend([frame(view, lit, 0.45)]
                                  * max(1, int(FPS * (each - 0.3))))
                last_state = (view, lit)
            else:
                hold(FPS * pause)
                rows.append([])      # breathe only when nothing was lit
                hold(FPS * 0.25)
        if last_state:               # a lit block is never shown unlit again
            pass
        else:
            hold(FPS * 0.15)
    # The tail frame must keep whatever the last stage lit. hold() renders the
    # block unlit, which dropped the highlight for the final two seconds.
    if last_state:
        view, lit = last_state
        frames.extend([frame(view, lit, 0.45)] * int(FPS * 2.0))
    else:
        hold(FPS * 2.0)
    return frames

def encode(frames, stem):
    tmp = pathlib.Path(tempfile.mkdtemp())
    for i, f in enumerate(frames): f.save(tmp / f"f{i:05d}.png")
    out = HERE.parent / "docs" / "images"
    out.mkdir(parents=True, exist_ok=True)
    mp4, gif, pal = out / f"{stem}.mp4", out / f"{stem}.gif", tmp / "pal.png"
    base = ["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS),
            "-i", str(tmp / "f%05d.png")]
    subprocess.run(base + ["-c:v", "libx264", "-pix_fmt", "yuv420p",
                           "-movflags", "+faststart", str(mp4)], check=True)
    subprocess.run(base + ["-vf", f"fps={FPS},scale=960:-1:flags=lanczos,palettegen=max_colors=160",
                           str(pal)], check=True)
    subprocess.run(base + ["-i", str(pal), "-lavfi",
                           f"fps={FPS},scale=960:-1:flags=lanczos[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=3",
                           str(gif)], check=True)
    shutil.rmtree(tmp, ignore_errors=True)
    return mp4, gif

if __name__ == "__main__":
    stem = sys.argv[1] if len(sys.argv) > 1 else "charter-demo"
    t = json.loads((HERE / "transcript.json").read_text())
    fr = build(t)
    print(f"{len(fr)} frames = {len(fr)/FPS:.1f}s at {FPS}fps")
    for p in encode(fr, stem):
        print(f"  {p.relative_to(HERE.parent)}  {p.stat().st_size/1e6:.2f} MB")
