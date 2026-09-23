#!/usr/bin/env python
# /// script
# requires-python = ">=3.10"
# dependencies = ["matplotlib>=3.8", "pillow>=10.0"]
# ///
"""Draw the ownership split in ``docs/auth/oauth-flow.md`` § The split, precisely.

That section is a table of eight rows alternating between "Charter" and "you".
A table can hold the order or the ownership; holding both at once is what a
reader cannot do from it, and it is the whole argument of the page — Charter
does two things, you own everything between them, and the reason `authorize()`
hands `state` and the PKCE verifier back to you is that *you* are the one still
standing there when the browser comes back.

So the same rows are drawn: two lanes for the two owners, one band across both
for the moment that happens on the authorization server and in neither, and a
bracket down the reader's own lane covering what their session has to hold
across it.

``STEPS`` and ``SPAN`` below are the canonical copy in this file, and
``tests/test_docs_oauth.py`` asserts every one of their phrases is a row of that
table — so the picture and the prose cannot drift.

Run (uv builds the drawing dependencies into a throwaway environment; neither
matplotlib nor pillow is a dependency of the library or its test suite)::

    uv run scripts/generate_split_diagram.py

Writes docs/images/oauth-split-light.webp and -dark.webp.
"""

from __future__ import annotations

# Only the stdlib at module scope, on purpose: tests/test_docs_oauth.py imports
# this file for STEPS and SPAN, and does it in the project environment, which
# has no matplotlib in it. The drawing imports live inside render().
from pathlib import Path
from typing import List, NamedTuple, Tuple

ROOT = Path(__file__).resolve().parent.parent
IMAGES = ROOT / "docs" / "images"

CHARTER = "charter"
YOU = "you"
SERVER = "server"


class Step(NamedTuple):
    owner: str
    symbol: str  # the call, where one party's ownership is a function
    phrase: str  # the table's own words for what happens


# The rows of the table, in order. `phrase` is quoted from it rather than
# paraphrased, which is what lets the test compare the two directly.
STEPS: List[Step] = [
    Step(
        CHARTER,
        "flow.authorize()",
        "authorization URL, PKCE verifier + challenge, `state` generation",
    ),
    Step(SERVER, "", "the redirect, the consent screen"),
    Step(YOU, "", "the callback route"),
    Step(YOU, "states_match()", "verifying `state`"),
    Step(CHARTER, "flow.exchange()", "code → tokens"),
    Step(YOU, "", "storing the refresh token"),
    Step(CHARTER, "OAuth2Client.from_grant(...)", "refreshing, caching, rotation from then on"),
]

# The row that is not a step but a duration — it is why the diagram exists.
SPAN = "holding `state` + verifier between redirect and callback"
SPAN_LABEL = "your session holds state + the PKCE verifier across the redirect"

# The two lanes are the two owners the page argues about. The authorization
# server gets a band rather than a lane because it appears once, and because
# "this happens somewhere you do not control" is the thing worth drawing about
# it — a third column would make it look like a peer.
LANES = {CHARTER: "Charter", YOU: "You"}


class Palette(NamedTuple):
    name: str
    accent: str  # Charter's red — the docs' Signal Red, per theme
    accent_fill: str
    accent_edge: str
    ink: str  # your lane's text
    ink_fill: str
    ink_edge: str
    muted: str  # the server band, and the lane headers
    muted_edge: str
    arrow: str


LIGHT = Palette(
    name="light",
    accent="#C72C41",
    accent_fill="#C72C4114",
    accent_edge="#C72C4159",
    ink="#18181B",
    ink_fill="#0000000A",
    ink_edge="#00000026",
    muted="#71717A",
    muted_edge="#00000026",
    arrow="#00000038",
)

DARK = Palette(
    name="dark",
    accent="#E8586B",
    accent_fill="#E8586B24",
    accent_edge="#E8586B6B",
    ink="#FAFAFA",
    ink_fill="#FFFFFF0D",
    ink_edge="#FFFFFF2B",
    muted="#A1A1AA",
    muted_edge="#FFFFFF2B",
    arrow="#FFFFFF47",
)

# Geometry, in the same units the figure is sized in, so one number changes one
# thing. The canvas is 1000 wide because the docs column renders it at about
# two-thirds that, and everything here is legible at 0.66x.
W = 1000.0
MARGIN = 44.0
HEADER_Y = 44.0
CARD_GAP = 34.0  # deep enough for a connector to turn in
BAND_H = 74.0
AISLE = 44.0
SPAN_RESERVE = 200.0  # the bracket and its label live here, inside the canvas
LANE_W = (W - 2 * MARGIN - AISLE - SPAN_RESERVE) / 2
LANE_X = {CHARTER: MARGIN, YOU: MARGIN + LANE_W + AISLE}
PAD_X = 24.0
LINE_H = 25.0
SYMBOL_H = 31.0
CONTENT_TOP = 34.0  # clears the step number in the corner
PAD_BOTTOM = 18.0

# Type is sized against the rendered width, not the canvas. The docs column is
# about 630px, so the canvas lands at roughly 0.63 scale and a 15pt phrase
# arrives at about 13 CSS pixels — a step below body copy, which is where a
# diagram's labels belong. Sized for the canvas alone it came out at nine.


def _rows(line_counts: List[int]) -> Tuple[List[Tuple[Step, float, float]], float]:
    """Each step's top edge and height, stacked downward, and the total height.

    Heights come from how many lines the phrase actually wrapped to, measured
    against the real font — guessing produced a first card whose text ran out
    past its own lane and into the other one.
    """
    placed: List[Tuple[Step, float, float]] = []
    y = HEADER_Y + 38.0
    for step, lines in zip(STEPS, line_counts, strict=True):
        if step.owner == SERVER:
            height = BAND_H
        else:
            height = CONTENT_TOP + (SYMBOL_H if step.symbol else 0) + lines * LINE_H + PAD_BOTTOM
        placed.append((step, y, height))
        y += height + CARD_GAP
    return placed, y - CARD_GAP + MARGIN


def render(palette: Palette, out: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.font_manager import FontProperties, findfont
    from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

    def font(preferred: List[str], size: float, weight: str = "normal") -> FontProperties:
        """The installed families, in order, as one fallback chain.

        The chain matters rather than the winner: `code → tokens` is quoted from
        the table, and Helvetica Neue has no U+2192, so that string would render
        with a tofu box in it unless a font that does have the glyph is still in
        the list underneath. Matplotlib falls back per glyph, not per string, so
        the arrow comes from DejaVu and every other character stays in the face
        it was chosen for.
        """
        installed = []
        for family in preferred:
            try:
                findfont(FontProperties(family=family), fallback_to_default=False)
            except ValueError:
                continue
            installed.append(family)
        return FontProperties(family=[*installed, "DejaVu Sans"], size=size, weight=weight)

    SANS = ["Helvetica Neue", "Helvetica", "Arial"]
    MONO = ["Menlo", "SF Mono"]

    f_lane = font(SANS, 12.5, "bold")
    f_symbol = font(MONO, 15.5)
    f_phrase = font(SANS, 15.0)
    f_band = font(SANS, 15.0)
    f_band_sub = font(SANS, 12.5)
    f_span = font(SANS, 12.5)
    f_num = font(SANS, 11.0, "bold")

    # The figure exists before the layout does, because wrapping has to be
    # measured against the renderer. At dpi 100 with a figure W/100 inches wide,
    # one display pixel is one unit of the coordinate system below, so a width
    # measured here is directly comparable to LANE_W.
    fig = plt.figure(figsize=(W / 100.0, 10.0), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")
    fig.patch.set_alpha(0.0)
    renderer = fig.canvas.get_renderer()

    def measure(text: str, fp: FontProperties) -> float:
        handle = ax.text(0, 0, text, fontproperties=fp)
        width = handle.get_window_extent(renderer).width
        handle.remove()
        return width

    def wrap(text: str, fp: FontProperties, limit: float) -> List[str]:
        lines: List[str] = []
        current = ""
        for word in text.split():
            trial = f"{current} {word}".strip()
            if current and measure(trial, fp) > limit:
                lines.append(current)
                current = word
            else:
                current = trial
        if current:
            lines.append(current)
        return lines

    phrase_limit = LANE_W - 2 * PAD_X

    def fitted(symbol: str) -> FontProperties:
        """``f_symbol``, stepped down only as far as this symbol needs.

        A call name is one token and cannot be wrapped the way a phrase can, so
        the longest of them — ``OAuth2Client.from_grant(...)`` — sets its own
        size. Shrinking beats truncating: the label is quoted from the table,
        and a diagram reading ``OAuth2Client.from_gra`` is worse than one with a
        slightly smaller line in it.
        """
        width = measure(symbol, f_symbol)
        if width <= phrase_limit:
            return f_symbol
        scale = max(phrase_limit / width, 0.72)
        return font(MONO, f_symbol.get_size_in_points() * scale)

    wrapped = [
        wrap(step.phrase.replace("`", ""), f_phrase, phrase_limit)
        if step.owner != SERVER
        else [step.phrase.replace("`", "")]
        for step in STEPS
    ]
    placed, height = _rows([len(lines) for lines in wrapped])

    fig.set_size_inches(W / 100.0, height / 100.0)
    ax.set_xlim(0, W)
    ax.set_ylim(height, 0)  # y grows downward, the way the sequence reads

    # ---- lane headers
    for owner, label in LANES.items():
        ax.text(
            LANE_X[owner],
            HEADER_Y,
            label.upper(),
            fontproperties=f_lane,
            color=palette.muted,
            va="bottom",
            ha="left",
        )
        ax.plot(
            [LANE_X[owner], LANE_X[owner] + LANE_W],
            [HEADER_Y + 10, HEADER_Y + 10],
            color=palette.muted_edge,
            linewidth=1.0,
            solid_capstyle="butt",
        )

    def card(x, y, w, h, fill, edge, dashed=False):
        ax.add_patch(
            FancyBboxPatch(
                (x, y),
                w,
                h,
                boxstyle="round,pad=0,rounding_size=10",
                facecolor=fill,
                edgecolor=edge,
                linewidth=1.2,
                linestyle=(0, (4, 3.5)) if dashed else "solid",
                mutation_aspect=1,
            )
        )

    band_right = W - SPAN_RESERVE
    anchors: List[Tuple[float, float, float]] = []  # centre x, top, bottom

    for index, ((step, y, h), lines) in enumerate(zip(placed, wrapped, strict=True), start=1):
        if step.owner == SERVER:
            card(MARGIN, y, band_right - MARGIN, h, "none", palette.muted_edge, dashed=True)
            mid = (MARGIN + band_right) / 2
            ax.text(
                mid,
                y + h / 2 - 13,
                lines[0],
                fontproperties=f_band,
                color=palette.muted,
                va="center",
                ha="center",
            )
            ax.text(
                mid,
                y + h / 2 + 14,
                "on the authorization server — where neither of you is running",
                fontproperties=f_band_sub,
                color=palette.muted,
                va="center",
                ha="center",
                alpha=0.75,
            )
            anchors.append((mid, y, y + h))
            continue

        is_charter = step.owner == CHARTER
        x = LANE_X[step.owner]
        card(
            x,
            y,
            LANE_W,
            h,
            palette.accent_fill if is_charter else palette.ink_fill,
            palette.accent_edge if is_charter else palette.ink_edge,
        )
        keyed = palette.accent if is_charter else palette.ink

        # The number marks the corner; the text column starts underneath it,
        # never beside it.
        ax.text(
            x + PAD_X,
            y + 19,
            str(index),
            fontproperties=f_num,
            color=keyed,
            va="center",
            ha="left",
            alpha=0.55,
        )
        cursor = y + CONTENT_TOP
        if step.symbol:
            ax.text(
                x + PAD_X,
                cursor + 12,
                step.symbol,
                fontproperties=fitted(step.symbol),
                color=keyed,
                va="center",
                ha="left",
            )
            cursor += SYMBOL_H
        for line in lines:
            ax.text(
                x + PAD_X,
                cursor + LINE_H / 2,
                line,
                fontproperties=f_phrase,
                color=palette.muted if step.symbol else keyed,
                alpha=1.0 if step.symbol else 0.85,
                va="center",
                ha="left",
            )
            cursor += LINE_H
        anchors.append((x + LANE_W / 2, y, y + h))

    # ---- the handoffs. An elbow that turns inside the gap, rather than an arc:
    #      a curve across 400 units of lane has to bow far enough to cross the
    #      cards it is meant to connect.
    for (x0, _, bottom), (x1, top, _) in zip(anchors, anchors[1:], strict=False):
        turn = bottom + (top - bottom) / 2
        ax.plot(
            [x0, x0, x1],
            [bottom + 3, turn, turn],
            color=palette.arrow,
            linewidth=1.2,
            solid_capstyle="round",
            solid_joinstyle="round",
        )
        ax.add_patch(
            FancyArrowPatch(
                (x1, turn),
                (x1, top - 2),
                arrowstyle="-|>,head_length=4.5,head_width=2.8",
                color=palette.arrow,
                linewidth=1.2,
                shrinkA=0,
                shrinkB=0,
            )
        )

    # ---- the span: what your session carries while the browser is away. It
    #      opens where Charter hands `state` back and closes where you check it.
    top_edge = placed[0][1] + placed[0][2] + 8
    bottom_edge = placed[3][1] + placed[3][2] - 8
    bx = LANE_X[YOU] + LANE_W + 20
    ax.plot(
        [bx, bx + 9, bx + 9, bx],
        [top_edge, top_edge + 9, bottom_edge - 9, bottom_edge],
        color=palette.ink,
        linewidth=1.3,
        alpha=0.45,
        solid_capstyle="round",
        solid_joinstyle="round",
    )
    label_x = bx + 22
    label_lines = wrap(SPAN_LABEL, f_span, W - MARGIN - label_x)
    start = (top_edge + bottom_edge) / 2 - (len(label_lines) - 1) * 21 / 2
    for offset, line in enumerate(label_lines):
        ax.text(
            label_x,
            start + offset * 21,
            line,
            fontproperties=f_span,
            color=palette.ink,
            alpha=0.8,
            va="center",
            ha="left",
        )

    out.parent.mkdir(parents=True, exist_ok=True)
    png = out.with_suffix(".png")
    fig.savefig(png, dpi=200, transparent=True)
    plt.close(fig)

    from PIL import Image

    with Image.open(png) as image:
        image.save(out, "WEBP", lossless=True, quality=100, method=6)
    png.unlink()


def main() -> int:
    for palette in (LIGHT, DARK):
        out = IMAGES / f"oauth-split-{palette.name}.webp"
        render(palette, out)
        print(f"wrote docs/images/{out.name}  ({out.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
