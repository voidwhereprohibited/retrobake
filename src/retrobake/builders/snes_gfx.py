"""RetroBake's own pixel art and palettes for the SNES platformer engine (data only).

Everything here is original art drawn for RetroBake: no characters, tiles or colours are taken
from any existing game. The builder turns it into binary files the fixed engine template
``.INCBIN``s; nothing here is ever assembled as code.

Files (all sizes fixed):
- ``objtiles.bin``  8192 B  sprite sheet, 4bpp, 16x16 tiles of 8x8 (see ``SPRITE_IDS``)
- ``objpal.bin``     256 B  8 sprite palettes (BGR555)
- ``hudtiles.bin``          BG3 2bpp tiles: the font, then the HUD icons
- ``hudpal.bin``      64 B  BG3 palettes 0-7 (CGRAM 0-31)
- ``settings.bin``  30720 B 12 x 2560 B: per setting terrain + backdrop tiles, palettes, sky HDMA
- ``bg2map.bin``     8192 B 4 backdrop tilemaps (BG2, 32x32 entries of 16x16)
- ``ascii.bin``       128 B ASCII -> font tile number, for the engine's own fixed messages
"""

from __future__ import annotations

import colorsys
import random
from collections.abc import Callable

from . import snes_font

# --------------------------------------------------------------------------- encoding helpers

Grid = list[list[int]]


def bgr555(rgb: tuple[int, int, int]) -> int:
    r, g, b = (max(0, min(255, int(round(c)))) for c in rgb)
    return (b >> 3) << 10 | (g >> 3) << 5 | (r >> 3)


def pal_bytes(colors: list[tuple[int, int, int]], size: int = 16) -> bytes:
    cols = list(colors)[:size] + [(0, 0, 0)] * (size - len(colors))
    return b"".join(bgr555(c).to_bytes(2, "little") for c in cols)


def tile_4bpp(grid: Grid, ox: int, oy: int) -> bytes:
    """One 8x8 4bpp tile from ``grid`` at (ox, oy)."""
    lo = bytearray()
    hi = bytearray()
    for y in range(8):
        p = [0, 0, 0, 0]
        for x in range(8):
            v = grid[oy + y][ox + x] & 15
            for b in range(4):
                if v >> b & 1:
                    p[b] |= 0x80 >> x
        lo += bytes((p[0], p[1]))
        hi += bytes((p[2], p[3]))
    return bytes(lo + hi)


def tile_2bpp(grid: Grid) -> bytes:
    out = bytearray()
    for y in range(8):
        p0 = p1 = 0
        for x in range(8):
            v = grid[y][x] & 3
            if v & 1:
                p0 |= 0x80 >> x
            if v & 2:
                p1 |= 0x80 >> x
        out += bytes((p0, p1))
    return bytes(out)


def parse(rows: list[str], keys: dict[str, int]) -> Grid:
    width = len(rows[0])
    for r in rows:
        if len(r) != width:
            raise ValueError(f"ragged art row {r!r}")
    return [[keys[c] for c in r] for r in rows]


def blank(w: int = 16, h: int = 16) -> Grid:
    return [[0] * w for _ in range(h)]


# --------------------------------------------------------------------------- sprites

# Hero palette slots.
HERO_KEYS = {
    ".": 0, "k": 1, "s": 2, "S": 3, "o": 4, "O": 5, "h": 6, "H": 7,
    "w": 8, "b": 9, "B": 10, "e": 11, "m": 12, "M": 13, "g": 14, "r": 15,
}  # fmt: skip

HEADS: dict[str, list[str]] = {
    "knight": [
        "......kkkk......",
        ".....kmmmmk.....",
        "....kmmmmmmk....",
        "....kmmmmmmMk...",
        "....kMkkkkkMk...",
        "....kmmmmmmMk...",
        ".....kmmmmMk....",
        "......kkkkk.....",
    ],
    "explorer": [
        "................",
        "......kkkk......",
        ".....khhhhk.....",
        "..kkkhhhhhhkkk..",
        ".kHHHHHHHHHHHHk.",
        "....kssssesk....",
        "....kssssssk....",
        ".....kssssk.....",
    ],
    "robot": [
        "........k.......",
        "........g.......",
        ".....kkkkkk.....",
        "....kmmmmmmk....",
        "....kmwwmwwk....",
        "....kmmmmmmk....",
        "....kMkMkMMk....",
        ".....kkkkkk.....",
    ],
    "animal": [
        "....k.....k.....",
        "...khk...khk....",
        "...khhkkkhhk....",
        "...khhhhhhhhk...",
        "...khhhhhwekk...",
        "...khhhhwwwwk...",
        "....khhhhwwk....",
        ".....kkkkkk.....",
    ],
    "wizard": [
        "........kk......",
        ".......khhk.....",
        "......khhhk.....",
        ".....khhghhk....",
        "...kkhhhhhhhkk..",
        "....kssssesk....",
        "....kwwwwwwk....",
        ".....kwwwwk.....",
    ],
    "kid": [
        "................",
        "......kkkkk.....",
        ".....khhhhhk....",
        ".....khhhhhhkk..",
        "....kkHHHHHHHHk.",
        "....kbssssesk...",
        "....kssssssk....",
        ".....kssssk.....",
    ],
    "ninja": [
        "................",
        ".....kkkkkk.....",
        "....khhhhhhk....",
        "...kgggggggk....",
        "kggkhsssesHk....",
        ".k.khhhhhhhk....",
        "....khhhhhhk....",
        ".....kkkkkk.....",
    ],
    "pilot": [
        "................",
        "......kkkk......",
        ".....kbbbbk.....",
        "....kbbbbbbk....",
        "....kmwkmwkb....",
        "....ksssssbk....",
        "....kssssssk....",
        ".....kssssk.....",
    ],
}

BODIES: dict[str, list[str]] = {
    "stand": [
        ".....koooOk.....",
        "....koooooOk....",
        "...ksoooooOsk...",
        "...ksOoooOOsk...",
        "....kOOOOOOk....",
        "....kbbkkbbk....",
        "....kbbk.kbbk...",
        "...kBBBk.kBBBk..",
    ],
    "walk1": [
        ".....koooOk.....",
        "....koooooOk....",
        "...ksoooooOOk...",
        "....kOoooOOsk...",
        "....kOOOOOOk....",
        "...kbbkk.kbbk...",
        "..kbbk....kBBk..",
        "..kBBk.....kk...",
    ],
    "walk2": [
        ".....koooOk.....",
        "....koooooOk....",
        "...kOoooooOsk...",
        "...ksOoooOOk....",
        "....kOOOOOOk....",
        ".....kbbbbk.....",
        "....kbbkBBk.....",
        "....kBBk.kk.....",
    ],
    "jump": [
        "..ks.koooOk.sk..",
        "...kkoooooOkk...",
        "....koooooOk....",
        "....kOoooOOk....",
        "....kOOOOOOk....",
        "...kbbk.kbbk....",
        "..kBBk...kbbk...",
        "...kk.....kBBk..",
    ],
}

HERO_COLORS: dict[str, dict[str, tuple[int, int, int]]] = {
    # outfit o, accessory h, plus fixed skin/boots/metal
    "knight": {"o": (64, 104, 200), "h": (200, 48, 48)},
    "explorer": {"o": (96, 152, 72), "h": (176, 128, 64)},
    "robot": {"o": (232, 160, 40), "h": (120, 200, 232)},
    "animal": {"o": (64, 160, 184), "h": (232, 128, 48)},
    "wizard": {"o": (104, 64, 176), "h": (72, 48, 152)},
    "kid": {"o": (224, 64, 64), "h": (48, 96, 208)},
    "ninja": {"o": (56, 56, 80), "h": (40, 40, 56)},
    "pilot": {"o": (88, 120, 72), "h": (152, 96, 56)},
}

ENEMY_KEYS = {
    ".": 0,
    "k": 1,
    "o": 2,
    "O": 3,
    "p": 4,
    "w": 5,
    "e": 6,
    "b": 7,
    "B": 8,
    "y": 9,
    "Y": 10,
    "r": 11,
}  # noqa: E501

WALKER = [
    [
        "................",
        "................",
        "................",
        "......kkkk......",
        "....kkppppkk....",
        "...kpppppppOk...",
        "..kpwwkppppOOk..",
        "..kpwekpppOOOk..",
        ".kpppppppOOOOOk.",
        ".kOpppppOOOOOOk.",
        ".kOOOOOOOOOOOOk.",
        "..kkkkkkkkkkkk..",
        "...kbbk..kbbk...",
        "...kbBk..kbBk...",
        "...kkkk..kkkk...",
        "................",
    ],
    [
        "................",
        "................",
        "................",
        "................",
        "......kkkk......",
        "....kkppppkk....",
        "...kpwwkpppOk...",
        "..kppwekppOOOk..",
        ".kpppppppOOOOOk.",
        ".kOpppppOOOOOOk.",
        ".kOOOOOOOOOOOOk.",
        "..kkkkkkkkkkkk..",
        "..kbbk....kbbk..",
        "..kBBk....kBBk..",
        "..kkkk....kkkk..",
        "................",
    ],
]

HOPPER = [
    [
        "................",
        "................",
        "....kk....kk....",
        "...kyyk..kyyk...",
        "...kwek..kwek...",
        "..kyyyykkyyyyk..",
        ".kyyyyyyyyyyyYk.",
        ".kyyrrrrrrryyYk.",
        ".kyyyrrrrryyYYk.",
        ".kYyyyyyyyyYYYk.",
        "..kYYYYYYYYYYk..",
        "...kkkkkkkkkk...",
        "..kYYk....kYYk..",
        ".kYYYk....kYYYk.",
        ".kkkk......kkkk.",
        "................",
    ],
    [
        "....kk....kk....",
        "...kyyk..kyyk...",
        "...kwek..kwek...",
        "..kyyyykkyyyyk..",
        ".kyyyyyyyyyyyYk.",
        ".kyyyrrrrryyyYk.",
        ".kYyyyyyyyyyYYk.",
        "..kYYYYYYYYYYk..",
        "...kkkkkkkkkk...",
        "....kYk..kYk....",
        "....kYk..kYk....",
        "...kYYk..kYYk...",
        "..kYYk....kYYk..",
        "..kkk......kkk..",
        "................",
        "................",
    ],
]

FLYER = [
    [
        "................",
        "................",
        "k.............k.",
        "kk...........kk.",
        "kOk...kkkk..kOk.",
        "kOOk.kppppk.kOOk",
        ".kOOkppwwppkOOk.",
        ".kOOkpwweppkOOk.",
        "..kOkppwwppkOk..",
        "...kkppppppkk...",
        ".....kppppk.....",
        "......kOOk......",
        ".......kk.......",
        "................",
        "................",
        "................",
    ],
    [
        "................",
        "................",
        "................",
        "................",
        "......kkkk......",
        ".....kppppk.....",
        "kkkkkppwwppkkkkk",
        "kOOOkpwweppkOOOk",
        ".kOOkppwwppkOOk.",
        "..kkkppppppkkk..",
        ".....kppppk.....",
        "......kOOk......",
        ".......kk.......",
        "................",
        "................",
        "................",
    ],
]

BOSS = [
    [
        "................................",
        "....kk....................kk....",
        "...kyyk..................kyyk...",
        "...kyyk..................kyyk...",
        "....kyyk................kyyk....",
        "....kyyykkkkkkkkkkkkkkkkyyyk....",
        ".....kkooooooooooooooooookk.....",
        "....koooooooooooooooooooooOk....",
        "...kooooooooooooooooooooooOOk...",
        "...koookkkkooooooookkkkoooOOk...",
        "..koookwwwwkooooookwwwwkooOOOk..",
        "..koookwweekoooooookweewkoOOOk..",
        "..koooookkkooooooooookkkooOOOk..",
        "..koooooooooooooooooooooooOOOk..",
        "..kooooooookkkkkkkkkoooooooOOk..",
        "..kOooooookrwrwrwrwrkooooooOOk..",
        "..kOOooooookrrrrrrrkooooooOOOk..",
        "..kOOOooooookkkkkkkooooooOOOOk..",
        "..kOOOOooooooooooooooooOOOOOOk..",
        ".kkOOOOOOOooooooooooOOOOOOOOOkk.",
        "kooOOOOOOOOOOOOOOOOOOOOOOOOOOook",
        "koOkOOOOOOOOOOOOOOOOOOOOOOOOkOok",
        "kokkOOOOOOOOOOOOOOOOOOOOOOOOkkok",
        ".k..kOOOOOOOOOOOOOOOOOOOOOOk..k.",
        "....kOOOOOOOOOOOOOOOOOOOOOOk....",
        ".....kOOOOOOOOkkOOOOOOOOOOk.....",
        "......kkkkkkkk..kkkkkkkkkk......",
        ".....kbbbbbbk....kbbbbbbk.......",
        "....kbbbbbbbk....kbbbbbbbk......",
        "....kBBBBBBBk....kBBBBBBBk......",
        "....kkkkkkkkk....kkkkkkkkk......",
        "................................",
    ],
]

ITEM_KEYS = {
    ".": 0,
    "k": 1,
    "y": 2,
    "Y": 3,
    "w": 4,
    "r": 5,
    "R": 6,
    "c": 7,
    "C": 8,
    "b": 9,
    "B": 10,
    "g": 11,
    "G": 12,
    "m": 13,
    "M": 14,
    "p": 15,
}  # noqa: E501

GEM = [
    [
        "................",
        "................",
        "......kkkk......",
        ".....kwccCk.....",
        "....kwccccCk....",
        "...kwcccccCCk...",
        "...kcccccCCCk...",
        "...kCcccCCCCk...",
        "....kCCCCCCk....",
        ".....kCCCCk.....",
        "......kCCk......",
        ".......kk.......",
        "................",
        "................",
        "................",
        "................",
    ],
    [
        "................",
        "................",
        ".......kk.......",
        "......kwCk......",
        "......kwCk......",
        ".....kwccCk.....",
        ".....kccCCk.....",
        ".....kcCCCk.....",
        "......kCCk......",
        "......kCCk......",
        ".......kk.......",
        "................",
        "................",
        "................",
        "................",
        "................",
    ],
]

ITEMS: dict[str, list[str]] = {
    "heart": [
        "................",
        "................",
        "...kkk....kkk...",
        "..krrRk..krrRk..",
        ".krwrrRkkrrrRRk.",
        ".krwrrrrrrrrRRk.",
        ".krrrrrrrrrrRRk.",
        "..krrrrrrrrRRk..",
        "...krrrrrrRRk...",
        "....krrrrRRk....",
        ".....krrRRk.....",
        "......kRRk......",
        ".......kk.......",
        "................",
        "................",
        "................",
    ],
    "life": [
        "................",
        ".....kkkkkk.....",
        "....kgggggGk....",
        "...kgwggggGGk...",
        "...kggggggGGk...",
        "...kgggggGGGk...",
        "....kGGGGGGk....",
        ".....kkkkkk.....",
        "....kyyyyyYk....",
        "...kywyyyyYYk...",
        "...kyykkkyYYk...",
        "...kyykYYkYYk...",
        "...kyykkkkYYk...",
        "...kyyyyyYYYk...",
        "....kYYYYYYk....",
        ".....kkkkkk.....",
    ],
    "key": [
        "................",
        "................",
        "....kkkk........",
        "...kywyYk.......",
        "..kyk..kYk......",
        "..kyk..kYk......",
        "...kyyyYkkkkkkk.",
        "....kkkkyyyyyYYk",
        "........kkkkyk.k",
        "...........kYk..",
        "...........kk...",
        "................",
        "................",
        "................",
        "................",
        "................",
    ],
    "shop": [
        "................",
        ".kkkkkkkkkkkkkk.",
        ".kbbbbbbbbbbbbk.",
        ".kbkkkbkkbkkkbk.",
        ".kbkyybkcbkrkbk.",
        ".kbkyybkcbkrkbk.",
        ".kbkkkbkkbkkkbk.",
        ".kbbbbbbbbbbbbk.",
        ".kBBBBBBBBBBBBk.",
        ".kkkkkkBkkkkkkk.",
        "......kBk.......",
        "......kBk.......",
        "......kBk.......",
        "......kBk.......",
        ".....kBBBk......",
        "....kkkkkkk.....",
    ],
    "flag": [
        "..kk............",
        "..kwk...........",
        "..kmkkkkkkkk....",
        "..kmkrrrrrrrk...",
        "..kmkrrwwrrrRk..",
        "..kmkrwwwwrrRRk.",
        "..kmkrrwwrrRRk..",
        "..kmkrrrrrRRk...",
        "..kmkkkkkkkk....",
        "..kmk...........",
        "..kmk...........",
        "..kmk...........",
        "..kmk...........",
        "..kmk...........",
        "..kmk...........",
        "..kMk...........",
    ],
    "pole": [
        "..kmk...........",
        "..kmk...........",
        "..kmk...........",
        "..kmk...........",
        "..kmk...........",
        "..kmk...........",
        "..kmk...........",
        "..kmk...........",
        "..kmk...........",
        "..kmk...........",
        "..kmk...........",
        "..kmk...........",
        ".kMMMk..........",
        "kMMMMMk.........",
        "kMMMMMk.........",
        "kkkkkkk.........",
    ],
    "shot": [
        "................",
        "................",
        "................",
        "................",
        "................",
        "......kkkk......",
        ".....kwwyYk.....",
        "....kwwyyYYk....",
        "....kwyyyYYk....",
        ".....kYYYYk.....",
        "......kkkk......",
        "................",
        "................",
        "................",
        "................",
        "................",
    ],
    "slash": [
        "................",
        "....kk..........",
        "....kwk.........",
        ".....kwk........",
        ".....kwmk.......",
        "......kwmk......",
        "......kwmmk.....",
        "......kwmmk.....",
        "......kwmmk.....",
        "......kwmk......",
        ".....kwmk.......",
        ".....kwk........",
        "....kwk.........",
        "....kk..........",
        "................",
        "................",
    ],
    "poof": [
        "................",
        "................",
        "...w.......w....",
        "....w..w..w.....",
        ".....kwwwk......",
        "...kwwyyywwk....",
        "..wwyyYYYyyww...",
        "...kwyYYYywk....",
        "..wwyyYYYyyww...",
        "...kwwyyywwk....",
        ".....kwwwk......",
        "....w..w..w.....",
        "...w.......w....",
        "................",
        "................",
        "................",
    ],
}

# Sprite ids in the 16x16 sheet: id n -> 8x8 tile (n % 8) * 2 + (n // 8) * 32.
SPRITE_IDS = {
    "hero_stand": 0, "hero_walk1": 1, "hero_walk2": 2, "hero_jump": 3,
    "walker0": 4, "walker1": 5, "hopper0": 6, "hopper1": 7,
    "flyer0": 8, "flyer1": 9, "gem0": 10, "gem1": 11,
    "heart": 12, "life": 13, "key": 14, "shop": 15,
    "flag": 16, "pole": 17, "shot": 18, "slash": 19, "poof": 20,
}  # fmt: skip
BOSS_TILES = (128, 132)  # 32x32 frames (tile numbers)


def _hero(archetype: str, body: str) -> Grid:
    head = HEADS[archetype] if archetype in HEADS else HEADS["explorer"]
    return parse(head + BODIES[body], HERO_KEYS)


def _place16(sheet: Grid, sid: int, grid: Grid) -> None:
    ox, oy = (sid % 8) * 16, (sid // 8) * 16
    for y in range(16):
        for x in range(16):
            sheet[oy + y][ox + x] = grid[y][x]


def obj_tiles(archetype: str) -> bytes:
    sheet = blank(128, 128)
    for name in ("stand", "walk1", "walk2", "jump"):
        _place16(sheet, SPRITE_IDS[f"hero_{name}"], _hero(archetype, name))
    for i, art in enumerate(WALKER):
        _place16(sheet, SPRITE_IDS[f"walker{i}"], parse(art, ENEMY_KEYS))
    for i, art in enumerate(HOPPER):
        _place16(sheet, SPRITE_IDS[f"hopper{i}"], parse(art, ENEMY_KEYS))
    for i, art in enumerate(FLYER):
        _place16(sheet, SPRITE_IDS[f"flyer{i}"], parse(art, ENEMY_KEYS))
    for i, art in enumerate(GEM):
        _place16(sheet, SPRITE_IDS[f"gem{i}"], parse(art, ITEM_KEYS))
    for name, art in ITEMS.items():
        _place16(sheet, SPRITE_IDS[name], parse(art, ITEM_KEYS))
    boss0 = parse(BOSS[0], ENEMY_KEYS)
    boss1 = [row[:] for row in boss0[:26]] + [  # frame 2: feet swapped
        list(r)
        for r in parse(
            [
                ".......kbbbbbbk....kbbbbbbk.....",
                "......kbbbbbbbk....kbbbbbbbk....",
                "......kBBBBBBBk....kBBBBBBBk....",
                "......kkkkkkkkk....kkkkkkkkk....",
                "................................",
                "................................",
            ],
            ENEMY_KEYS,
        )
    ]
    for frame, grid in zip(BOSS_TILES, (boss0, boss1), strict=True):
        ox, oy = (frame % 16) * 8, (frame // 16) * 8
        for y in range(32):
            for x in range(32):
                sheet[oy + y][ox + x] = grid[y][x]
    out = bytearray()
    for ty in range(16):
        for tx in range(16):
            out += tile_4bpp(sheet, tx * 8, ty * 8)
    assert len(out) == 8192
    return bytes(out)


# --------------------------------------------------------------------------- colours


def _shade(rgb: tuple[int, int, int], f: float) -> tuple[int, int, int]:
    if f >= 1:
        return tuple(int(c + (255 - c) * (f - 1)) for c in rgb)  # type: ignore[return-value]
    return tuple(int(c * f) for c in rgb)  # type: ignore[return-value]


MOODS: dict[str, Callable[[tuple[float, float, float]], tuple[float, float, float]]] = {
    # HLS transforms (h, lum, s) -> (h, lum, s)
    "bright": lambda h, lum, s: (h, lum, min(1.0, s * 1.2)),
    "pastel": lambda h, lum, s: (h, lum + (1 - lum) * 0.35, s * 0.6),
    "warm": lambda h, lum, s: ((h + (0.07 - h) * 0.25) % 1.0, lum, s),
    "earthy": lambda h, lum, s: (h, lum * 0.92, s * 0.7),
    "icy": lambda h, lum, s: ((h + (0.58 - h) * 0.25) % 1.0, min(1.0, lum * 1.05), s * 0.85),
    "neon": lambda h, lum, s: (h, lum, min(1.0, s * 1.6 + 0.1)),
    "dark": lambda h, lum, s: (h, lum * 0.72, s),
    "spooky": lambda h, lum, s: ((h + (0.78 - h) * 0.3) % 1.0, lum * 0.8, s * 0.8),
}  # fmt: skip


def mood(rgb: tuple[int, int, int], name: str) -> tuple[int, int, int]:
    fn = MOODS.get(name)
    if fn is None:
        return rgb
    h, lum, s = colorsys.rgb_to_hls(*(c / 255 for c in rgb))
    h, lum, s = fn(h, lum, s)  # type: ignore[misc]
    r, g, b = colorsys.hls_to_rgb(h % 1.0, max(0.0, min(1.0, lum)), max(0.0, min(1.0, s)))
    return (int(r * 255), int(g * 255), int(b * 255))


# Setting order must match catalog()["settings"] (level record byte 8).
SETTINGS: list[dict] = [
    # grassland
    dict(sky=((88, 152, 248), (176, 224, 255)), top=(72, 184, 56), earth=(176, 112, 56),
         block=(200, 112, 64), plank=(184, 136, 80), far=(128, 200, 168), near=(72, 160, 96),
         cloud=(255, 255, 255), top_style="grass", hills="round", sky_style="cloud"),
    # forest
    dict(sky=((80, 152, 184), (176, 224, 208)), top=(40, 136, 48), earth=(120, 80, 48),
         block=(104, 104, 88), plank=(152, 104, 56), far=(40, 112, 72), near=(24, 80, 48),
         cloud=(224, 240, 232), top_style="grass", hills="pines", sky_style="cloud"),
    # castle
    dict(sky=((40, 40, 88), (120, 96, 152)), top=(168, 168, 176), earth=(112, 112, 124),
         block=(136, 128, 120), plank=(150, 100, 60), far=(80, 72, 112), near=(56, 48, 84),
         cloud=(160, 150, 190), top_style="stone", hills="towers", sky_style="cloud"),
    # cave
    dict(sky=((16, 16, 32), (56, 44, 72)), top=(136, 112, 96), earth=(88, 64, 56),
         block=(112, 96, 88), plank=(132, 92, 60), far=(64, 52, 72), near=(44, 36, 52),
         cloud=(90, 80, 100), top_style="rock", hills="spikes", sky_style="none"),
    # desert
    dict(sky=((232, 160, 88), (255, 224, 160)), top=(240, 208, 120), earth=(208, 160, 88),
         block=(200, 144, 96), plank=(168, 120, 72), far=(232, 192, 120), near=(208, 160, 96),
         cloud=(255, 240, 216), top_style="sand", hills="round", sky_style="cloud"),
    # ocean
    dict(sky=((64, 160, 240), (184, 232, 255)), top=(240, 224, 160), earth=(208, 184, 128),
         block=(176, 176, 184), plank=(176, 128, 80), far=(64, 144, 216), near=(40, 112, 192),
         cloud=(255, 255, 255), top_style="sand", hills="waves", sky_style="cloud"),
    # ice
    dict(sky=((152, 192, 240), (224, 240, 255)), top=(248, 252, 255), earth=(120, 160, 208),
         block=(160, 208, 240), plank=(168, 128, 96), far=(208, 228, 248), near=(160, 196, 232),
         cloud=(255, 255, 255), top_style="snow", hills="peaks", sky_style="cloud"),
    # volcano
    dict(sky=((64, 20, 24), (208, 80, 40)), top=(104, 80, 72), earth=(72, 44, 40),
         block=(128, 60, 44), plank=(120, 80, 56), far=(112, 40, 32), near=(72, 28, 28),
         cloud=(128, 104, 104), top_style="rock", hills="peaks", sky_style="cloud"),
    # city
    dict(sky=((80, 112, 200), (240, 176, 144)), top=(152, 152, 164), earth=(100, 100, 112),
         block=(176, 96, 80), plank=(120, 120, 136), far=(80, 88, 136), near=(56, 60, 100),
         cloud=(248, 208, 208), top_style="metal", hills="buildings", sky_style="cloud"),
    # space
    dict(sky=((6, 6, 20), (40, 20, 72)), top=(176, 184, 204), earth=(88, 96, 124),
         block=(120, 128, 156), plank=(140, 148, 170), far=(84, 64, 128), near=(60, 44, 96),
         cloud=(255, 255, 224), top_style="metal", hills="round", sky_style="stars"),
    # haunted
    dict(sky=((28, 14, 44), (92, 60, 108)), top=(100, 108, 76), earth=(72, 56, 64),
         block=(100, 92, 108), plank=(108, 80, 64), far=(56, 40, 72), near=(36, 28, 52),
         cloud=(136, 124, 156), top_style="grass", hills="pines", sky_style="stars"),
    # sky
    dict(sky=((112, 176, 255), (224, 244, 255)), top=(255, 255, 255), earth=(220, 228, 248),
         block=(216, 184, 104), plank=(200, 164, 112), far=(208, 228, 255), near=(176, 208, 252),
         cloud=(255, 255, 255), top_style="cloud", hills="round", sky_style="cloud"),
]  # fmt: skip

# Terrain palette slots (BG palette 2).
T_OUT, T_TOP1, T_TOP2, T_TOP3, T_E1, T_E2, T_E3 = 1, 2, 3, 4, 5, 6, 7
T_B1, T_B2, T_B3, T_P1, T_P2, T_M1, T_M2, T_GOLD = 8, 9, 10, 11, 12, 13, 14, 15


def terrain_palette(s: dict, m: str) -> list[tuple[int, int, int]]:
    top, earth, block, plank = s["top"], s["earth"], s["block"], s["plank"]
    cols = [
        (0, 0, 0),
        _shade(earth, 0.28),
        _shade(top, 1.25),
        top,
        _shade(top, 0.7),
        _shade(earth, 1.15),
        earth,
        _shade(earth, 0.7),
        _shade(block, 1.25),
        block,
        _shade(block, 0.65),
        _shade(plank, 1.2),
        _shade(plank, 0.7),
        (220, 224, 232),
        (128, 132, 148),
        (248, 200, 48),
    ]
    return [cols[0]] + [mood(c, m) for c in cols[1:]]


def backdrop_palette(s: dict, m: str) -> list[tuple[int, int, int]]:
    far, near, cloud = s["far"], s["near"], s["cloud"]
    cols = [
        (0, 0, 0),
        _shade(far, 1.15), far, _shade(far, 0.85),
        _shade(near, 1.15), near, _shade(near, 0.8),
        cloud, _shade(cloud, 0.85), _shade(cloud, 0.7),
        _shade(near, 1.6), (255, 240, 160),
    ]  # fmt: skip
    return [cols[0]] + [mood(c, m) for c in cols[1:]]


def sky_hdma(s: dict, m: str) -> bytes:
    """HDMA mode 3 table for CGRAM colour 0: 14 bands of 16 lines, then 0."""
    top, bottom = (mood(c, m) for c in s["sky"])
    out = bytearray()
    for band in range(14):
        t = band / 13
        c = tuple(int(a + (b - a) * t) for a, b in zip(top, bottom, strict=True))
        v = bgr555(c)  # type: ignore[arg-type]
        out += bytes((16, 0, 0, v & 0xFF, v >> 8))
    out.append(0)
    return bytes(out)


# --------------------------------------------------------------------------- terrain tiles


def _noise(seed: int) -> random.Random:
    return random.Random(seed)  # noqa: S311 - decorative pixel noise only


def _earth(g: Grid, y0: int, style: str, seed: int) -> None:
    rng = _noise(seed)
    for y in range(y0, 16):
        for x in range(16):
            g[y][x] = T_E2
    if style in ("stone", "metal"):
        for y in range(y0, 16):
            for x in range(16):
                edge = (y - y0) % 8 == 7 or (x + (4 if ((y - y0) // 8) % 2 else 0)) % 8 == 7
                g[y][x] = T_E3 if edge else (T_E1 if (y - y0) % 8 == 0 else T_E2)
        if style == "metal":
            for y, x in ((y0 + 2, 2), (y0 + 2, 13), (13, 2), (13, 13)):
                if y < 16:
                    g[y][x] = T_E1
        return
    for _ in range(9):
        x, y = rng.randrange(16), rng.randrange(y0, 16)
        g[y][x] = T_E3
        if x < 15:
            g[y][x + 1] = T_E1 if rng.random() < 0.5 else T_E3


def _ground(style: str) -> Grid:
    g = blank()
    _earth(g, 0, style, 11)
    if style == "grass":
        depth = [5, 4, 5, 6, 5, 4, 4, 5, 6, 5, 4, 5, 5, 6, 5, 4]
        for x in range(16):
            for y in range(depth[x]):
                g[y][x] = T_TOP2
            g[0][x] = T_TOP1
            g[depth[x]][x] = T_TOP3
        for x in (2, 7, 12):
            g[1][x] = T_TOP1
    elif style == "snow":
        depth = [4, 5, 5, 4, 4, 5, 6, 5, 4, 4, 5, 5, 4, 5, 6, 5]
        for x in range(16):
            for y in range(depth[x]):
                g[y][x] = T_TOP1 if y < 2 else T_TOP2
            g[depth[x]][x] = T_TOP3
    elif style == "sand":
        for x in range(16):
            for y in range(4):
                g[y][x] = T_TOP1 if y == 0 else T_TOP2
            g[4][x] = T_TOP3 if x % 3 else T_TOP2
        for x, y in ((3, 2), (9, 1), (13, 3)):
            g[y][x] = T_TOP3
    elif style == "cloud":
        depth = [5, 6, 6, 5, 4, 5, 6, 6, 5, 4, 5, 6, 6, 5, 4, 5]
        for x in range(16):
            for y in range(depth[x]):
                g[y][x] = T_TOP1 if y < 3 else T_TOP2
            g[depth[x]][x] = T_TOP3
    else:  # stone / rock / metal: a solid cap row
        for x in range(16):
            g[0][x] = T_TOP1
            g[1][x] = T_TOP2
            g[2][x] = T_TOP2
            g[3][x] = T_TOP3
        if style == "rock":
            for x in (4, 11):
                g[3][x] = T_TOP2
                g[4][x] = T_TOP3
        if style == "metal":
            for x in (1, 6, 9, 14):
                g[1][x] = T_TOP1
    return g


def _fill(style: str) -> Grid:
    g = blank()
    _earth(g, 0, style, 23)
    return g


def _block() -> Grid:
    g = blank()
    for y in range(16):
        for x in range(16):
            if y in (0, 15) or x in (0, 15) or y == 7 or (x == 7 and y < 7) or (x == 11 and y > 7):
                g[y][x] = T_B3
            elif y in (1, 8) or x in (1,):
                g[y][x] = T_B1
            else:
                g[y][x] = T_B2
    return g


def _platform() -> Grid:
    g = blank()
    for x in range(16):
        g[0][x] = T_OUT
        g[1][x] = T_P1
        g[2][x] = T_P1
        g[3][x] = T_P2 if x % 8 else T_OUT
        g[4][x] = T_P2
        g[5][x] = T_OUT
    for x in (2, 13):
        g[2][x] = T_M2
    for y in range(6, 9):
        g[y][3] = T_P2
        g[y][12] = T_P2
    return g


def _spikes() -> Grid:
    g = blank()
    for i in range(2):
        cx = 4 + i * 8
        for y in range(2, 13):
            half = (y - 2) * 4 // 10
            for x in range(cx - half - 1, cx + half + 1):
                if 0 <= x < 16:
                    g[y][x] = T_M1 if x < cx else T_M2
            g[y][max(0, cx - half - 2)] = T_OUT if y > 3 else g[y][max(0, cx - half - 2)]
    for y in range(13, 16):
        for x in range(16):
            g[y][x] = T_B3 if y == 13 else T_B2
    return g


def _door() -> Grid:
    g = blank()
    for y in range(16):
        for x in range(16):
            if x in (0, 15) or y == 0:
                g[y][x] = T_B3
            elif x in (1, 14) or y == 1:
                g[y][x] = T_OUT
            else:
                g[y][x] = T_P1 if (x - 2) % 4 else T_P2
    for y in range(5, 11):
        for x in range(6, 10):
            g[y][x] = T_GOLD if y < 10 else T_OUT
    g[7][7] = T_OUT
    g[7][8] = T_OUT
    g[8][7] = T_OUT
    g[9][7] = T_OUT
    return g


def _decor() -> Grid:
    g = blank()
    for y in range(9, 16):
        w = min(7, (y - 8) * 2)
        for x in range(8 - w, 8 + w):
            g[y][x] = T_TOP2 if (x + y) % 3 else T_TOP1
        g[y][8 - w] = T_TOP3
    return g


# --------------------------------------------------------------------------- backdrop tiles

B_FAR1, B_FAR2, B_FAR3, B_NEAR1, B_NEAR2, B_NEAR3, B_C1, B_C2, B_C3 = range(1, 10)
B_LIGHT, B_STAR = 10, 11


BACKDROP_VARIANT = {"round": 0, "pointy": 1, "flat": 2, "waves": 3}
HILL_STYLE = {
    "round": "round", "pines": "pointy", "spikes": "pointy", "peaks": "pointy",
    "towers": "flat", "buildings": "flat", "waves": "waves",
}  # fmt: skip


def _textured_fill(seed: int) -> Grid:
    rng = _noise(seed)
    g = [[B_FAR2] * 16 for _ in range(16)]
    for _ in range(6):
        g[rng.randrange(16)][rng.randrange(16)] = B_FAR3
    return g


def _backdrop_tiles(s: dict) -> list[Grid]:
    style = HILL_STYLE.get(s["hills"], "round")
    up, down, cap = blank(), blank(), blank()
    fill = _textured_fill(5)
    flat = [row[:] for row in fill]
    for x in range(16):
        flat[0][x] = flat[1][x] = B_FAR1
    for y in range(16):
        for x in range(16):
            if style == "pointy":
                if y >= 15 - x:
                    up[y][x] = B_FAR1 if y <= 16 - x else fill[y][x]
                if y >= x:
                    down[y][x] = B_FAR3 if y <= x + 1 else fill[y][x]
                if y >= abs(x - 7.5) * 2 - 1:
                    edge = y < abs(x - 7.5) * 2 + 1
                    cap[y][x] = (B_FAR1 if x < 8 else B_FAR3) if edge else fill[y][x]
            else:
                ru = 16 - (max(0, 256 - (16 - x) ** 2)) ** 0.5
                rd = 16 - (max(0, 256 - (x + 1) ** 2)) ** 0.5
                rc = 16 - (max(0.0, 64 - (x - 7.5) ** 2)) ** 0.5 * (
                    1.0 if style == "waves" else 1.6
                )
                if y >= ru:
                    up[y][x] = B_FAR1 if y < ru + 1.5 else fill[y][x]
                if y >= rd:
                    down[y][x] = B_FAR1 if y < rd + 1.5 else fill[y][x]
                if y >= rc:
                    cap[y][x] = B_FAR1 if y < rc + 1.5 else fill[y][x]
    if style == "flat":
        towers = s["hills"] == "towers"
        flat = blank()
        for y in range(16):
            for x in range(16):
                flat[y][x] = B_FAR3 if x >= 14 else B_FAR2
                if not towers and y % 4 == 2 and x % 4 in (1, 2) and x < 13:
                    flat[y][x] = B_STAR
                if towers and y < 3 and x % 6 in (3, 4, 5):
                    flat[y][x] = 0
                if towers and y in (7, 8) and x in (6, 7):
                    flat[y][x] = B_STAR
        fill = [row[:] for row in flat]
        for y in range(3):
            fill[y] = [B_FAR3 if x >= 14 else B_FAR2 for x in range(16)]
    sky1, sky2 = blank(), blank()
    if s["sky_style"] == "stars":
        for x, y in ((3, 4), (12, 9), (7, 13)):
            sky1[y][x] = B_STAR
        for x, y in ((9, 2), (2, 11), (14, 14), (6, 7)):
            sky2[y][x] = B_C1 if (x + y) % 2 else B_STAR
    elif s["sky_style"] == "cloud":
        for y in range(16):
            for x in range(16):
                d1 = ((x - 11) / 6) ** 2 + ((y - 10) / 5) ** 2
                d2 = ((x - 4) / 6) ** 2 + ((y - 10) / 5) ** 2
                d3 = ((x - 13) / 5) ** 2 + ((y - 7) / 5) ** 2
                if d1 <= 1 or (x >= 11 and 10 <= y < 15):
                    sky1[y][x] = B_C1 if y < 11 else (B_C2 if y < 14 else B_C3)
                if d2 <= 1 or d3 <= 1 or (x <= 4 and 10 <= y < 15):
                    sky2[y][x] = B_C1 if y < 11 else (B_C2 if y < 14 else B_C3)
    return [blank(), up, down, fill, cap, sky1, sky2, flat]


def setting_tiles(s: dict) -> bytes:
    style = s["top_style"]
    terrain = [
        blank(),
        _ground(style),
        _fill(style),
        _block(),
        _platform(),
        _spikes(),
        _door(),
        _decor(),
    ]  # noqa: E501
    backdrop = _backdrop_tiles(s)
    sheet = blank(128, 32)
    for i, g in enumerate(terrain):
        for y in range(16):
            for x in range(16):
                sheet[y][i * 16 + x] = g[y][x]
    for i, g in enumerate(backdrop):
        for y in range(16):
            for x in range(16):
                sheet[16 + y][i * 16 + x] = g[y][x]
    out = bytearray()
    for ty in range(4):
        for tx in range(16):
            out += tile_4bpp(sheet, tx * 8, ty * 8)
    assert len(out) == 2048
    return bytes(out)


SETTING_BYTES = 2560
# layout of one setting record (the engine reads these fixed offsets)
SETTING_OFFSETS = {
    "tiles": 0,
    "terrain_pal": 2048,
    "backdrop_pal": 2080,
    "hdma": 2112,
    "variant": 2240,
}  # noqa: E501


def settings_bin(palette_mood: str) -> bytes:
    out = bytearray()
    for s in SETTINGS:
        blob = setting_tiles(s)
        blob += pal_bytes(terrain_palette(s, palette_mood))
        blob += pal_bytes(backdrop_palette(s, palette_mood))
        blob += sky_hdma(s, palette_mood)
        blob = blob.ljust(SETTING_OFFSETS["variant"], b"\x00")
        blob += bytes([BACKDROP_VARIANT[HILL_STYLE.get(s["hills"], "round")]])
        out += blob.ljust(SETTING_BYTES, b"\x00")
    assert len(out) == 12 * SETTING_BYTES
    return bytes(out)


HEIGHTS = {
    0: [2, 3, 3, 4, 4, 3, 2, 2, 3, 4, 5, 5, 4, 3, 2, 1, 1, 2, 3, 3, 2, 2, 3, 4, 4, 3, 3, 2, 2, 3, 2, 2],  # noqa: E501
    1: [1, 2, 3, 4, 5, 4, 3, 2, 1, 2, 3, 4, 3, 2, 1, 1, 2, 3, 4, 5, 6, 5, 4, 3, 2, 1, 2, 3, 2, 1, 1, 1],  # noqa: E501
    2: [3, 3, 5, 5, 5, 2, 2, 4, 4, 6, 6, 6, 3, 3, 3, 5, 5, 2, 2, 2, 4, 4, 4, 6, 6, 3, 3, 5, 5, 5, 2, 2],  # noqa: E501
    3: [2, 2, 2, 3, 2, 2, 2, 2, 3, 2, 2, 2, 2, 2, 3, 2, 2, 2, 3, 2, 2, 2, 2, 3, 2, 2, 2, 2, 2, 3, 2, 2],  # noqa: E501
}  # fmt: skip


def bg2_map(variant: int = 0) -> bytes:
    """One backdrop BG2 map (32x32 entries): clouds up high, hills along the bottom."""
    pal = 4 << 10
    heights = HEIGHTS[variant]
    rows = [[0] * 32 for _ in range(32)]
    base = 13  # bottom visible row
    for c in range(32):
        h = heights[c]
        hl, hr = heights[c - 1], heights[(c + 1) % 32]
        top = base - h + 1
        for r in range(top + 1, 14):
            rows[r][c] = 3
        if variant == 2:
            rows[top][c] = 7
        elif hl < h and hr < h:
            rows[top][c] = 4
        elif hl < h:
            rows[top][c] = 1
        elif hr < h:
            rows[top][c] = 2
        else:
            rows[top][c] = 7 if variant != 1 else 4
    for c, r in ((2, 2), (7, 5), (17, 2), (24, 4), (29, 3), (13, 5), (4, 6), (21, 6)):
        rows[r][c] = 5
        rows[r][(c + 1) % 32] = 6
    out = bytearray()
    for r in range(32):
        for c in range(32):
            m = rows[r][c]
            out += (0 if m == 0 else ((32 + m * 2) | pal)).to_bytes(2, "little")
    return bytes(out)


def bg2_maps() -> bytes:
    """bg2map.bin: the four backdrop variants, 2 KB each (setting record byte picks one)."""
    return b"".join(bg2_map(v) for v in range(4))


# --------------------------------------------------------------------------- sprite palettes

GREY = [(0, 0, 0)] + [
    (v, v, v) for v in (24, 210, 160, 140, 100, 180, 120, 255, 80, 60, 30, 200, 150, 220, 110)
]  # noqa: E501


def obj_palettes(archetype: str, palette_mood: str) -> bytes:
    hc = HERO_COLORS.get(archetype, HERO_COLORS["explorer"])
    o, h = hc["o"], hc["h"]
    hero = [
        (0, 0, 0), (24, 16, 24), (248, 200, 160), (208, 144, 112),
        o, _shade(o, 0.65), h, _shade(h, 0.65),
        (255, 255, 255), (136, 84, 48), (88, 52, 32), (24, 16, 24),
        (200, 208, 224), (120, 128, 152), (248, 200, 48), (224, 64, 64),
    ]  # fmt: skip
    enemy = [
        (0, 0, 0), (24, 12, 24), (176, 72, 176), (120, 40, 128), (208, 96, 200),
        (255, 255, 255), (24, 12, 24), (112, 72, 40), (72, 44, 24),
        (120, 200, 72), (72, 144, 48), (232, 64, 72), (0, 0, 0), (0, 0, 0), (0, 0, 0), (0, 0, 0),
    ]  # fmt: skip
    items = [
        (0, 0, 0), (24, 16, 24), (248, 216, 64), (200, 144, 32), (255, 255, 255),
        (240, 64, 72), (168, 32, 48), (96, 216, 240), (40, 136, 200), (176, 120, 72),
        (120, 76, 44), o, _shade(o, 0.65), (208, 212, 224), (128, 132, 148), (0, 0, 0),
    ]  # fmt: skip
    boss = [
        (0, 0, 0), (24, 12, 16), (160, 88, 64), (104, 52, 40), (0, 0, 0),
        (255, 255, 255), (24, 12, 16), (96, 64, 48), (64, 40, 28),
        (232, 216, 168), (184, 160, 112), (232, 64, 48), (0, 0, 0), (0, 0, 0), (0, 0, 0), (0, 0, 0),
    ]  # fmt: skip
    hurt = [(0, 0, 0)] + [(255, 255, 255)] * 15
    pals = [hero, enemy, items, boss, hurt, GREY, items, items]
    return b"".join(pal_bytes([p[0]] + [mood(c, palette_mood) if i > 1 and n in (1, 3) else c
                                        for i, c in enumerate(p[1:], 1)])
                    for n, p in enumerate(pals))  # fmt: skip


# --------------------------------------------------------------------------- HUD font + icons

ICON_KEYS = {".": 0, "1": 1, "2": 2, "3": 3}
ICONS: dict[str, list[str]] = {
    "heart": [
        ".11..11.",
        "1221122.",
        "12222221",
        "12222221",
        ".122221.",
        "..1221..",
        "...11...",
        "........",
    ],  # noqa: E501
    "heart_empty": [
        ".11..11.",
        "1..11..1",
        "1......1",
        "1......1",
        ".1....1.",
        "..1..1..",
        "...11...",
        "........",
    ],  # noqa: E501
    "gem": [
        "...11...",
        "..1331..",
        ".133331.",
        "13333331",
        ".133331.",
        "..1331..",
        "...11...",
        "........",
    ],  # noqa: E501
    "life": [
        "..1111..",
        ".133331.",
        "13133131",
        "13333331",
        "13133131",
        ".131131.",
        "..1111..",
        "........",
    ],  # noqa: E501
    "key": [
        ".11.....",
        "1331....",
        "13.31111",
        "1331.1.1",
        ".11.....",
        "........",
        "........",
        "........",
    ],  # noqa: E501
    "times": [
        "........",
        "........",
        ".1...1..",
        "..1.1...",
        "...1....",
        "..1.1...",
        ".1...1..",
        "........",
    ],  # noqa: E501
}
ICON_TILES = {name: len(snes_font.CHARSET) + i for i, name in enumerate(ICONS)}


def hud_tiles() -> bytes:
    out = bytearray(snes_font.font_bin())
    for rows in ICONS.values():
        out += tile_2bpp(parse(rows, ICON_KEYS))
    return bytes(out)


def hud_palettes() -> bytes:
    pals = [
        [(0, 0, 0), (255, 255, 255), (200, 200, 200), (120, 120, 120)],  # 0 text
        [(0, 0, 0), (40, 16, 24), (232, 56, 64), (248, 208, 64)],  # 1 hearts / key
        [(0, 0, 0), (16, 32, 56), (200, 240, 255), (80, 200, 240)],  # 2 gem
        [(0, 0, 0), (24, 16, 24), (248, 200, 160), (248, 224, 96)],  # 3 life icon
        [(0, 0, 0), (255, 224, 96), (200, 140, 40), (60, 30, 10)],  # 4 gold text
        [(0, 0, 0)] * 4,
        [(0, 0, 0)] * 4,
        [(0, 0, 0)] * 4,
    ]
    return b"".join(pal_bytes(p, 4) for p in pals)


def ascii_table() -> bytes:
    out = bytearray(128)
    for i, ch in enumerate(snes_font.CHARSET):
        out[ord(ch)] = i
        if ch.isalpha():
            out[ord(ch.lower())] = i
    return bytes(out)
