"""RetroBake's own 5x7 pixel font (original glyphs) + the cover title banner."""

from __future__ import annotations

from .raster import Canvas, Color

_GLYPHS = {
    "A": ".###.|#...#|#...#|#####|#...#|#...#|#...#",
    "B": "####.|#...#|#...#|####.|#...#|#...#|####.",
    "C": ".###.|#...#|#....|#....|#....|#...#|.###.",
    "D": "####.|#...#|#...#|#...#|#...#|#...#|####.",
    "E": "#####|#....|#....|####.|#....|#....|#####",
    "F": "#####|#....|#....|####.|#....|#....|#....",
    "G": ".###.|#...#|#....|#.###|#...#|#...#|.####",
    "H": "#...#|#...#|#...#|#####|#...#|#...#|#...#",
    "I": ".###.|..#..|..#..|..#..|..#..|..#..|.###.",
    "J": "..###|...#.|...#.|...#.|...#.|#..#.|.##..",
    "K": "#...#|#..#.|#.#..|##...|#.#..|#..#.|#...#",
    "L": "#....|#....|#....|#....|#....|#....|#####",
    "M": "#...#|##.##|#.#.#|#.#.#|#...#|#...#|#...#",
    "N": "#...#|#...#|##..#|#.#.#|#..##|#...#|#...#",
    "O": ".###.|#...#|#...#|#...#|#...#|#...#|.###.",
    "P": "####.|#...#|#...#|####.|#....|#....|#....",
    "Q": ".###.|#...#|#...#|#...#|#.#.#|#..#.|.##.#",
    "R": "####.|#...#|#...#|####.|#.#..|#..#.|#...#",
    "S": ".####|#....|#....|.###.|....#|....#|####.",
    "T": "#####|..#..|..#..|..#..|..#..|..#..|..#..",
    "U": "#...#|#...#|#...#|#...#|#...#|#...#|.###.",
    "V": "#...#|#...#|#...#|#...#|#...#|.#.#.|..#..",
    "W": "#...#|#...#|#...#|#.#.#|#.#.#|#.#.#|.#.#.",
    "X": "#...#|#...#|.#.#.|..#..|.#.#.|#...#|#...#",
    "Y": "#...#|#...#|.#.#.|..#..|..#..|..#..|..#..",
    "Z": "#####|....#|...#.|..#..|.#...|#....|#####",
    "0": ".###.|#...#|#..##|#.#.#|##..#|#...#|.###.",
    "1": "..#..|.##..|..#..|..#..|..#..|..#..|.###.",
    "2": ".###.|#...#|....#|...#.|..#..|.#...|#####",
    "3": "####.|....#|....#|.###.|....#|....#|####.",
    "4": "...#.|..##.|.#.#.|#..#.|#####|...#.|...#.",
    "5": "#####|#....|####.|....#|....#|#...#|.###.",
    "6": ".###.|#....|#....|####.|#...#|#...#|.###.",
    "7": "#####|....#|...#.|..#..|.#...|.#...|.#...",
    "8": ".###.|#...#|#...#|.###.|#...#|#...#|.###.",
    "9": ".###.|#...#|#...#|.####|....#|....#|.###.",
    ".": ".....|.....|.....|.....|.....|.##..|.##..",
    ",": ".....|.....|.....|.....|.##..|..#..|.#...",
    "!": "..#..|..#..|..#..|..#..|..#..|.....|..#..",
    "?": ".###.|#...#|....#|...#.|..#..|.....|..#..",
    "'": "..#..|..#..|.#...|.....|.....|.....|.....",
    "&": ".##..|#..#.|#.#..|.#...|#.#.#|#..#.|.##.#",
    ":": ".....|.##..|.##..|.....|.##..|.##..|.....",
    "-": ".....|.....|.....|#####|.....|.....|.....",
    " ": ".....|.....|.....|.....|.....|.....|.....",
}
GLYPH_W, GLYPH_H, ADVANCE = 5, 7, 6
CHARSET = frozenset(_GLYPHS) | frozenset("abcdefghijklmnopqrstuvwxyz")
_ROWS = {k: [r for r in v.split("|")] for k, v in _GLYPHS.items()}


def text_width(text: str, scale: int) -> int:
    return max(0, len(text) * ADVANCE - 1) * scale


def draw_text(canvas: Canvas, text: str, x: int, y: int, scale: int, color: Color) -> None:
    """Draw ``text`` (unknown characters become spaces, lowercase drawn uppercase)."""
    for n, ch in enumerate(text.upper()):
        rows = _ROWS.get(ch, _ROWS[" "])
        gx = x + n * ADVANCE * scale
        for ry, row in enumerate(rows):
            for rx, bit in enumerate(row):
                if bit == "#":
                    canvas.fill_rect(gx + rx * scale, y + ry * scale, scale, scale, color)


def _lines(title: str, width: int, max_scale: int) -> tuple[list[str], int]:
    words = title.split()
    options = [[title]]
    if len(words) > 1:
        best = min(
            range(1, len(words)),
            key=lambda i: abs(len(" ".join(words[:i])) - len(" ".join(words[i:]))),
        )
        options.append([" ".join(words[:best]), " ".join(words[best:])])
    scored = []
    for lines in options:
        longest = max(len(line) for line in lines)
        scale = max(1, min(max_scale, (width + 1) // max(1, longest * ADVANCE)))
        scored.append((scale, -len(lines), lines))
    scale, _, lines = max(scored)
    return lines, scale


def add_title_banner(canvas: Canvas, title: str, *, bg: Color, fg: Color, shadow: Color) -> None:
    """Draw the game title in a banner across the top of the cover."""
    title = " ".join(title.split())[:24] or "My Game"
    pad = max(8, canvas.width // 32)
    lines, scale = _lines(title, canvas.width - 4 * pad, max_scale=max(2, canvas.width // 90))
    line_h = (GLYPH_H + 3) * scale
    band_h = len(lines) * line_h + 2 * pad
    canvas.blend_rect(0, 0, canvas.width, band_h, bg, 0.82)
    canvas.fill_rect(0, band_h, canvas.width, max(2, scale), fg)
    y = pad + scale
    for line in lines:
        x = (canvas.width - text_width(line, scale)) // 2
        draw_text(canvas, line, x + scale, y + scale, scale, shadow)
        draw_text(canvas, line, x, y, scale, fg)
        y += line_h
