"""RetroBake's own NES graphics for the platformer engine (original art, GPL-3.0-or-later).

Builds the 8 KB CHR-ROM: pattern table 0 (background) and pattern table 1 (sprites).
Pixel values: "." 0 (transparent/backdrop), "a" 1 (outline/dark), "b" 2 (main), "c" 3 (light).

Tile map (keep in step with templates/nes/platformer/main.s):
  BG  0-44   font (nes_font.CHARSET)
  BG  64+4*(t-1) .. +3  metatile t (1 ground .. 7 decor), order TL TR BL BR
  SPR 0-44   font drawn in colour 3 (HUD digits)
  SPR 64 hero A, 68 hero B (walk), 72 walker, 76 hopper, 80 flyer, 84 coin, 88 heart,
      92 life, 96 key, 100-115 boss (32x32, rows of 4), 116 shop, 120 goal flag
  SPR 124 shot, 125 coin icon, 126 heart icon, 127 life icon, 128 key icon, 129 sword
"""

from __future__ import annotations

from . import nes_font

_PX = {".": 0, "a": 1, "b": 2, "c": 3}


def _grid(lines: list[str], w: int = 16, h: int = 16) -> list[list[int]]:
    rows = [line.ljust(w, ".")[:w] for line in lines] + ["." * w] * (h - len(lines))
    if len(rows) != h or any(set(r) - set(_PX) for r in rows):
        raise ValueError("bad art")
    return [[_PX[p] for p in r] for r in rows[:h]]


def _sym(halves: list[str]) -> list[str]:
    return [h.ljust(8, ".")[:8] + h.ljust(8, ".")[:8][::-1] for h in halves]


def _tile8(g: list[list[int]], ox: int = 0, oy: int = 0) -> bytes:
    p0 = bytearray(8)
    p1 = bytearray(8)
    for y in range(8):
        for x in range(8):
            v = g[oy + y][ox + x]
            if v & 1:
                p0[y] |= 0x80 >> x
            if v & 2:
                p1[y] |= 0x80 >> x
    return bytes(p0 + p1)


def _meta(g: list[list[int]]) -> bytes:
    """16x16 grid -> 4 tiles TL TR BL BR."""
    return b"".join(_tile8(g, ox, oy) for oy, ox in ((0, 0), (0, 8), (8, 0), (8, 8)))


def _scale2(g: list[list[int]]) -> list[list[int]]:
    return [[v for v in row for _ in (0, 1)] for row in g for _ in (0, 1)]


# ---------------------------------------------------------------- background metatiles


def _ground() -> list[list[int]]:
    g = _grid(["cccccccccccccccc", "ccbcccccbccccbcc", "abbabbbabbbabbab"])
    for y in range(3, 16):
        g[y] = [1 if (x * 7 + y * 5) % 11 == 0 else 2 for x in range(16)]
    return g


def _fill() -> list[list[int]]:
    return [[1 if (x * 7 + y * 5) % 11 == 0 else 2 for x in range(16)] for y in range(16)]


def _block() -> list[list[int]]:
    g = [[2] * 16 for _ in range(16)]
    for y in range(16):
        band = y // 4
        joints = (7, 15) if band % 2 == 0 else (3, 11)
        for x in range(16):
            if y % 4 == 0 or x in joints:
                g[y][x] = 1
            elif y % 4 == 1:
                g[y][x] = 3
    return g


def _platform() -> list[list[int]]:
    return _grid(["c" * 16, "cbbbbbbbbbbbbbbc", "b" * 16, "bbabbbbbbbbbbabb", "a" * 16])


def _spikes() -> list[list[int]]:
    g = [[0] * 16 for _ in range(16)]
    for y in range(14):
        half = (y + 2) / 4
        for x in range(16):
            d = (x % 8) - 3.5
            if abs(d) < half:
                g[y][x] = 1 if abs(d) > half - 1 else (3 if d < 0 else 2)
    for y in (14, 15):
        g[y] = [1] * 16
    return g


def _door() -> list[list[int]]:
    g = [[2] * 16 for _ in range(16)]
    for y in range(16):
        for x in range(16):
            if x in (0, 15) or y == 0 or x in (5, 10):
                g[y][x] = 1
    g[9][12] = g[9][13] = g[10][12] = g[10][13] = 3
    return g


def _decor() -> list[list[int]]:
    return _grid(
        [""] * 9
        + ["......c..c......", ".....cbccbc.....", "....cbbcbbbc....", "...abbbbbbbba..."]
        + ["..abbbbbbbbbba..", "..aaaaaaaaaaaa.."]
    )


METATILES = [_ground, _fill, _block, _platform, _spikes, _door, _decor]  # tile ids 1..7

# ---------------------------------------------------------------- sprites

HERO_A = [
    "",
    ".....aaaaa",
    "....abbbbba",
    "...abbbbbbba",
    "...aaaaaaaaaa",
    "....accacca",
    "....acccccca",
    ".....acccca",
    "....abbbbbba",
    "...acabbbbaca",
    "...acabbbbaca",
    "....abbbbbba",
    "....aabbbbaa",
    "....ab.aa.ba",
    "...aaa....aaa",
]
HERO_B = HERO_A[:12] + ["....aabbbbaa", ".....abaabba", "....aaa..aaa", ""]

WALKER = _sym(
    [
        "",
        "",
        ".....aaa",
        "....abbb",
        "...abbbb",
        "..abbcab",
        "..abbcab",
        "..abbbbb",
        "..abbbbb",
        "..abbaaa",
        "...abbbb",
        "....aaaa",
        "...abba.",
        "...aaaa.",
    ]
)
HOPPER = _sym(
    [
        "",
        "",
        "....aa..",
        "...acca.",
        "...acaa.",
        "...abbbb",
        "..abbbbb",
        "..abbbbb",
        "..abbaaa",
        "...abbbb",
        "....abbb",
        "...abba.",
        "..abba..",
        "..aaa...",
    ]
)
FLYER = _sym(
    [
        "",
        "",
        "aa......",
        "abaa....",
        "abbbaa.a",
        ".abbbbab",
        "..abbbbb",
        "...abcab",
        "...abbbb",
        "....abba",
        ".....aab",
        "......aa",
    ]
)
COIN = _sym(
    [
        "",
        "",
        "......aa",
        ".....acc",
        "....accb",
        "....acbb",
        "....acbb",
        "....acbb",
        "....acbb",
        "....acbb",
        "....accb",
        ".....acc",
        "......aa",
    ]
)
HEART = _sym(
    [
        "",
        "",
        "..aaa...",
        ".abbba..",
        "abccbba.",
        "abcbbbba",
        "abbbbbbb",
        "abbbbbbb",
        ".abbbbbb",
        "..abbbbb",
        "...abbbb",
        "....abbb",
        ".....abb",
        "......ab",
        ".......a",
    ]
)
LIFE = _sym(
    [
        "",
        "",
        "....aaaa",
        "...abbbb",
        "..abbbbb",
        ".aaaaaaa",
        "..accccc",
        "..acaccc",
        "..accccc",
        "...acccc",
        "....aaaa",
    ]
)
KEY = [
    "",
    "",
    "",
    "...aaaa",
    "..acccca",
    ".acaaaaca",
    ".aca..aca",
    ".acaaaaca",
    "..accccaaaaaaaa",
    "...aaaaccccccca",
    ".......aacaacaa",
    "........a.a..a",
]
BOSS = _sym(
    [
        "..a.....",
        ".aba....",
        ".abaaaaa",
        "..abbbbb",
        ".abbbbbb",
        "abbccbbb",
        "abcaacbb",
        "abbccbbb",
        "abbbbbbb",
        "abbaaaaa",
        "abbacaca",
        "abbbbbbb",
        ".abbbbbb",
        "..aabbbb",
        "..abba..",
        "..aaaa..",
    ]
)
SHOP = _sym(
    [
        "",
        "",
        "......aa",
        ".....abb",
        "......aa",
        ".....abb",
        "...aabbb",
        "..abbbbb",
        ".abbbccc",
        ".abbbcab",
        ".abbbccc",
        "..abbbbb",
        "...aaaaa",
    ]
)
FLAG = [
    ".aa",
    ".acaaaaaaaa",
    ".acbbbbbbbba",
    ".acbbcbbbbbba",
    ".acbbbbbbbba",
    ".acaaaaaaaa",
    ".ac",
    ".ac",
    ".ac",
    ".ac",
    ".ac",
    ".ac",
    ".ac",
    ".ac",
    ".aa",
    "aaaa",
]
SMALL = [  # 8x8 tiles from 124
    ["", "..aaa", ".accca", ".acbca", ".accca", "..aaa"],  # shot
    ["", "..aaa", ".acbba", ".acbba", ".acbba", "..aaa"],  # coin icon
    ["", ".aa.aa", "abbabba", "abbbbba", ".abbba", "..aba", "...a"],  # heart icon
    ["", "..aaa", ".abbba", "aaaaaaa", ".accca", ".acaca", "..aaa"],  # life icon
    ["", ".aa", "acca", "acaaaaaa", "accaccca", ".aa.a.a"],  # key icon
    ["", "......aa", ".....aca", "....aca", ".a.aca", "..aca", ".aaa", "a.a"],  # sword
]


def _font_tile(ch: str, colour: int) -> bytes:
    plain = nes_font.chr_bank()[nes_font.CHARSET.index(ch) * 16 :][:8]
    return bytes(plain) + (bytes(plain) if colour == 3 else bytes(8))


def _table(tiles: dict[int, bytes]) -> bytes:
    out = bytearray(4096)
    for idx, data in tiles.items():
        if len(data) % 16 or idx * 16 + len(data) > 4096:
            raise ValueError("tile overflow")
        out[idx * 16 : idx * 16 + len(data)] = data
    return bytes(out)


def chr_bank() -> bytes:
    """8 KB CHR-ROM for the platformer engine."""
    bg = {i: _font_tile(c, 1) for i, c in enumerate(nes_font.CHARSET)}
    for t, make in enumerate(METATILES, start=1):
        bg[64 + 4 * (t - 1)] = _meta(make())
    spr = {i: _font_tile(c, 3) for i, c in enumerate(nes_font.CHARSET)}
    for idx, art in (
        (64, HERO_A),
        (68, HERO_B),
        (72, WALKER),
        (76, HOPPER),
        (80, FLYER),
        (84, COIN),
        (88, HEART),
        (92, LIFE),
        (96, KEY),
        (116, SHOP),
        (120, FLAG),
    ):
        spr[idx] = _meta(_grid(art))
    big = _scale2(_grid(BOSS))
    spr[100] = b"".join(_tile8(big, x * 8, y * 8) for y in range(4) for x in range(4))
    for i, art in enumerate(SMALL):
        spr[124 + i] = _tile8(_grid(art, 8, 8))
    return _table(bg) + _table(spr)
