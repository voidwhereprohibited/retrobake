"""Placeholder graphics for the NES platformer engine, drawn in code (original RetroBake art).

Background pattern table ($0000): RetroBake's font in tiles $00-$3F, then four tiles per level
metatile from ``META_BASE`` (top-left, top-right, bottom-left, bottom-right). Sprite pattern
table ($1000): hero (tiles 0-3, 2x2), key (4), goal flag (5 top, 6 bottom).
"""

from __future__ import annotations

from collections.abc import Callable

from retrobake.spec import levels as lv

from . import nes_font

META_BASE = 0x40
TABLE_BYTES = 4096
CHR_BYTES = 8192

Grid = list[list[int]]


def _grid(size_x: int, size_y: int, paint: Callable[[int, int], int]) -> Grid:
    return [[paint(x, y) for x in range(size_x)] for y in range(size_y)]


def _tile(grid: Grid, ox: int, oy: int) -> bytes:
    lo, hi = bytearray(8), bytearray(8)
    for y in range(8):
        for x in range(8):
            c = grid[oy + y][ox + x]
            lo[y] |= (c & 1) << (7 - x)
            hi[y] |= (c >> 1 & 1) << (7 - x)
    return bytes(lo + hi)


def _quad(grid: Grid) -> bytes:
    return b"".join(_tile(grid, ox, oy) for oy, ox in ((0, 0), (0, 8), (8, 0), (8, 8)))


# Colours: 0 sky, 1 light, 2 earth, 3 dark.
def _ground(x: int, y: int) -> int:
    if y < 3:
        return 3
    return 1 if (x * 7 + y * 3) % 11 == 0 else 2


def _fill(x: int, y: int) -> int:
    if (x * 5 + y * 7) % 13 == 0:
        return 1
    return 3 if (x + y * 3) % 17 == 0 else 2


def _block(x: int, y: int) -> int:
    if x in (0, 15) or y in (0, 15):
        return 3
    return 1 if x == y or x == 15 - y else 2


def _platform(x: int, y: int) -> int:
    if y == 0:
        return 1
    if y in (1, 2):
        return 2
    if y == 3 or (4 <= y <= 6 and x in (2, 13)):
        return 3
    return 0


def _spikes(x: int, y: int) -> int:
    if y == 15:
        return 3
    if y >= 8 and abs((x % 8) - 3.5) <= (y - 8) / 2:
        return 1
    return 0


def _door(x: int, y: int) -> int:
    if x in (0, 15) or y == 0:
        return 0
    if x in (1, 14) or y == 1:
        return 3
    return 1 if x == 11 and y in (9, 10) else 2


def _decor(x: int, y: int) -> int:
    if x == 8 and 10 <= y <= 15:
        return 3
    if (x, y) == (8, 8):
        return 2
    return 1 if (x, y) in ((7, 8), (9, 8), (8, 7), (8, 9)) else 0


METATILES: dict[int, Callable[[int, int], int]] = {
    lv.EMPTY: lambda x, y: 0,
    lv.GROUND: _ground,
    lv.FILL: _fill,
    lv.BLOCK: _block,
    lv.PLATFORM: _platform,
    lv.SPIKES: _spikes,
    lv.DOOR: _door,
    lv.DECOR: _decor,
}


# Sprite colours: hero 1 shirt, 2 skin, 3 dark; items 1 gold, 2 white, 3 dark.
def _hero(x: int, y: int) -> int:
    if y <= 1 and 4 <= x <= 11:
        return 3
    if y <= 6 and 4 <= x <= 11:
        return 3 if (x, y) == (9, 3) else 2
    if 7 <= y <= 11 and 3 <= x <= 12:
        return 1
    if y >= 12 and (4 <= x <= 6 or 9 <= x <= 11):
        return 3
    return 0


def _key(x: int, y: int) -> int:
    if 1 <= y <= 4 and 0 <= x <= 3 and not (y in (2, 3) and x in (1, 2)):
        return 1
    if y == 2 and 4 <= x <= 7 or (x in (5, 7) and y == 3):
        return 1
    return 0


def _flag(x: int, y: int) -> int:
    if x == 1:
        return 3
    return 1 if 2 <= x <= 7 and 1 <= y <= 6 else 0


def _heart(x: int, y: int) -> int:
    if y in (1, 2) and x in (1, 2, 4, 5):
        return 1
    return 1 if 3 <= y <= 5 and y - 2 <= x <= 8 - y else 0


# Enemy colours: 1 body, 2 white, 3 dark.
def _walker(x: int, y: int) -> int:
    if y >= 13:
        return 3 if x in (2, 3, 4, 11, 12, 13) else 0
    if (x - 7.5) ** 2 + (y - 8) ** 2 > 42:
        return 0
    if y in (5, 6) and x in (4, 5, 10, 11):
        return 2 if x in (4, 10) else 3
    return 1


def _patroller(x: int, y: int) -> int:
    if y <= 3:
        return 2 if (x < 7 and y >= x // 2) or (x > 8 and y >= (15 - x) // 2) else 0
    if not (2 <= x <= 13 and y <= 12):
        return 0
    if y in (6, 7) and x in (5, 10):
        return 3
    return 1


# Sprite tiles: 0-3 hero, 4 key, 5-6 flag, 7 heart, 8-11 walker, 12-15 patroller.
def sprite_table() -> bytes:
    hero = _grid(16, 16, _hero)
    flag = _grid(8, 16, _flag)
    out = _quad(hero) + _tile(_grid(8, 8, _key), 0, 0) + _tile(flag, 0, 0) + _tile(flag, 0, 8)
    out += _tile(_grid(8, 8, _heart), 0, 0)
    out += _quad(_grid(16, 16, _walker)) + _quad(_grid(16, 16, _patroller))
    return out + bytes(TABLE_BYTES - len(out))


def background_table() -> bytes:
    font = nes_font.chr_bank()[: META_BASE * 16]
    if len(nes_font.CHARSET) > META_BASE:
        raise ValueError("the font overlaps the metatile tiles")
    meta = b"".join(_quad(_grid(16, 16, METATILES[t])) for t in range(len(METATILES)))
    out = font + meta
    return out + bytes(TABLE_BYTES - len(out))


def chr_rom() -> bytes:
    data = background_table() + sprite_table()
    assert len(data) == CHR_BYTES
    return data
