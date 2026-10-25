"""Engine-neutral level data (contract "level-data", see docs/level-data.md).

A level is a grid of 16x16 "metatiles", ``HEIGHT`` rows tall and a whole number of 16-column
screens wide, plus a list of objects. Both engines read the same data, either as Python objects
(``Level``) or as the compact binary pack from ``LevelPack.encode()``.

Coordinates: ``x`` = column (0 = left), ``y`` = row (0 = top). A ground object at ``(x, y)``
stands on the tile at ``(x, y + 1)``.
"""

from __future__ import annotations

import struct
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from .catalog import catalog

FORMAT_VERSION = 1
HEIGHT = 12  # rows of metatiles; fits NES (15 rows) and SNES (14 rows) with room for a HUD
SCREEN_WIDTH = 16  # metatiles per screen

# Tile ids (4 bits).
EMPTY, GROUND, FILL, BLOCK, PLATFORM, SPIKES, DOOR, DECOR = range(8)
TILES = {
    EMPTY: "empty",
    GROUND: "ground",  # solid, top surface of the ground
    FILL: "fill",  # solid, earth under the ground surface
    BLOCK: "block",  # solid block / pillar / wall
    PLATFORM: "platform",  # one-way: stand on top, jump up through it
    SPIKES: "spikes",  # solid and hurts on touch; never needed to stand on
    DOOR: "door",  # solid until the hero has the key, then opens
    DECOR: "decor",  # background decoration, not solid
}
SOLID = frozenset({GROUND, FILL, BLOCK, SPIKES, DOOR})
SUPPORT = frozenset({GROUND, FILL, BLOCK, PLATFORM, DOOR})  # you can stand on these

# Object kinds (1 byte).
WALKER, HOPPER, FLYER, COIN, HEART, LIFE, KEY, BOSS, SHOP = range(1, 10)
OBJECTS = {
    WALKER: "walker",  # walks along the ground, turns at walls and ledges
    HOPPER: "hopper",  # hops in place / toward the hero
    FLYER: "flyer",  # floats in a slow wave around its start point
    COIN: "coin",  # collectible
    HEART: "heart",  # restores one heart (or one hit)
    LIFE: "life",  # extra life
    KEY: "key",  # opens the level's door
    BOSS: "boss",  # 2x2 metatiles, (x, y) is its bottom-left; goal opens when it's beaten
    SHOP: "shop",  # shop sign: spend coins
}
ENEMIES = frozenset({WALKER, HOPPER, FLYER, BOSS})

# The generator never needs a jump higher than ``rise`` tiles, or landing more than ``reach``
# columns away at the same or lower height (reach - 1 for one tile up, 2 for two up).
# Engines must give the hero at least a 3-tile-high, 5-tile-long jump so this has margin.
JUMP = {"rise": 2, "reach": 4}

# Max bytes for the whole encoded pack, per system (engines size their ROM data for this).
BUDGETS = {"nes": 6144, "snes": 32768}
MAX_OBJECTS = {"nes": 40, "snes": 96}
MAX_SCREENS = {"nes": 8, "snes": 16}
SYSTEM_IDS = {"nes": 0, "snes": 1}


@dataclass(frozen=True)
class Obj:
    kind: int
    x: int
    y: int

    def to_dict(self) -> dict[str, Any]:
        return {"kind": OBJECTS[self.kind], "x": self.x, "y": self.y}


@dataclass
class Level:
    index: int
    width: int  # columns, a multiple of SCREEN_WIDTH
    tiles: list[bytearray]  # HEIGHT rows of ``width`` tile ids
    objects: list[Obj]
    start: tuple[int, int]
    goal: tuple[int, int]
    setting: str
    boss: bool = False
    key_door: bool = False
    time_limit: int = 0  # seconds, 0 = no limit

    @property
    def screens(self) -> int:
        return self.width // SCREEN_WIDTH

    def tile(self, x: int, y: int) -> int:
        if 0 <= x < self.width and 0 <= y < HEIGHT:
            return self.tiles[y][x]
        return EMPTY

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "width": self.width,
            "height": HEIGHT,
            "setting": self.setting,
            "boss": self.boss,
            "key_door": self.key_door,
            "time_limit": self.time_limit,
            "start": {"x": self.start[0], "y": self.start[1]},
            "goal": {"x": self.goal[0], "y": self.goal[1]},
            "rows": ["".join(f"{t:x}" for t in row) for row in self.tiles],
            "objects": [o.to_dict() for o in self.objects],
        }

    def encode(self) -> bytes:
        """Binary level record. Layout in docs/level-data.md."""
        flags = (1 if self.boss else 0) | (2 if self.key_door else 0)
        settings = list(catalog()["settings"])
        out = bytearray(
            struct.pack(
                "<BBHBBBBBB",
                self.screens,
                flags,
                self.time_limit,
                *self.start,
                *self.goal,
                settings.index(self.setting),
                len(self.objects),
            )
        )
        for o in sorted(self.objects, key=lambda o: (o.x, o.y, o.kind)):
            out += bytes((o.kind, o.x, o.y))
        x = 0
        while x < self.width:
            col = self._column_runs(x)
            repeat = 1
            while repeat < 16 and x + repeat < self.width and self._column_runs(x + repeat) == col:
                repeat += 1
            out.append(((repeat - 1) << 4) | len(col))
            out += bytes((t << 4) | (n - 1) for t, n in col)
            x += repeat
        return bytes(out)

    def _column_runs(self, x: int) -> list[tuple[int, int]]:
        runs: list[tuple[int, int]] = []
        for y in range(HEIGHT):
            t = self.tiles[y][x]
            if runs and runs[-1][0] == t:
                runs[-1] = (t, runs[-1][1] + 1)
            else:
                runs.append((t, 1))
        return runs


def decode_level(data: bytes, index: int = 0) -> Level:
    """Reference decoder for the binary record (engines port this; tests use it)."""
    screens, flags, time_limit, sx, sy, gx, gy, setting, count = struct.unpack_from(
        "<BBHBBBBBB", data
    )
    pos = struct.calcsize("<BBHBBBBBB")
    objects = []
    for _ in range(count):
        objects.append(Obj(data[pos], data[pos + 1], data[pos + 2]))
        pos += 3
    width = screens * SCREEN_WIDTH
    tiles = [bytearray(width) for _ in range(HEIGHT)]
    x = 0
    while x < width:
        head = data[pos]
        pos += 1
        repeat, nruns = (head >> 4) + 1, head & 0x0F
        column: list[int] = []
        for _ in range(nruns):
            b = data[pos]
            pos += 1
            column += [b >> 4] * ((b & 0x0F) + 1)
        if len(column) != HEIGHT:
            raise ValueError("bad column")
        for _ in range(repeat):
            for y in range(HEIGHT):
                tiles[y][x] = column[y]
            x += 1
    return Level(
        index=index,
        width=width,
        tiles=tiles,
        objects=objects,
        start=(sx, sy),
        goal=(gx, gy),
        setting=list(catalog()["settings"])[setting],
        boss=bool(flags & 1),
        key_door=bool(flags & 2),
        time_limit=time_limit,
    )


@dataclass
class LevelPack:
    system: str
    seed: int
    levels: list[Level] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": "retrobake-levels",
            "version": FORMAT_VERSION,
            "system": self.system,
            "seed": self.seed,
            "height": HEIGHT,
            "screen_width": SCREEN_WIDTH,
            "jump": dict(JUMP),
            "tiles": {str(k): v for k, v in TILES.items()},
            "objects": {str(k): v for k, v in OBJECTS.items()},
            "levels": [lv.to_dict() for lv in self.levels],
        }

    def encode(self) -> bytes:
        """``RBLV`` pack: header, u16 offset table, level records. See docs/level-data.md."""
        blobs = [lv.encode() for lv in self.levels]
        head = 4 + 3 + 2 * len(blobs)
        out = bytearray(b"RBLV")
        out += bytes((FORMAT_VERSION, SYSTEM_IDS[self.system], len(blobs)))
        offset = head
        for b in blobs:
            out += struct.pack("<H", offset)
            offset += len(b)
        for b in blobs:
            out += b
        return bytes(out)


def decode_pack(data: bytes) -> LevelPack:
    if data[:4] != b"RBLV" or data[4] != FORMAT_VERSION:
        raise ValueError("not a RetroBake level pack")
    system = {v: k for k, v in SYSTEM_IDS.items()}[data[5]]
    count = data[6]
    pack = LevelPack(system=system, seed=0)
    for i in range(count):
        (off,) = struct.unpack_from("<H", data, 7 + 2 * i)
        pack.levels.append(decode_level(data[off:], i))
    return pack


# --- playability -------------------------------------------------------------------------------


def _standable(level: Level, x: int, y: int, door_open: bool) -> bool:
    if not (0 <= x < level.width and 0 <= y < HEIGHT - 1):
        return False
    here, below = level.tile(x, y), level.tile(x, y + 1)
    if door_open and here == DOOR:
        here = EMPTY
    if door_open and below == DOOR:
        return False
    return here not in SOLID and below in SUPPORT


def _blocked(level: Level, x: int, y: int, door_open: bool, tiles: frozenset[int]) -> bool:
    t = level.tile(x, max(y, 0))
    if door_open and t == DOOR:
        return False
    return t in tiles


def _moves(level: Level, x: int, y: int, door_open: bool):
    for dx in range(-JUMP["reach"], JUMP["reach"] + 1):
        if dx == 0:
            continue
        tx = x + dx
        for ty in range(max(0, y - JUMP["rise"]), HEIGHT - 1):
            rise = y - ty
            if rise > 0 and abs(dx) > JUMP["reach"] - rise:
                continue
            if not _standable(level, tx, ty, door_open):
                continue
            apex = max(0, min(y, ty) - 2)
            if any(_blocked(level, x, r, door_open, SOLID) for r in range(apex, y)):
                continue
            step = 1 if dx > 0 else -1
            if any(
                _blocked(level, c, r, door_open, SOLID)
                for c in range(x + step, tx, step)
                for r in range(apex, min(y, ty) + 1)
            ):
                continue
            if any(_blocked(level, tx, r, door_open, SUPPORT) for r in range(apex, ty)):
                continue
            yield tx, ty


def reachable(level: Level, door_open: bool = False) -> set[tuple[int, int]]:
    """Standing cells the hero can reach from the start using only ``JUMP`` moves."""
    seen = {level.start}
    todo = deque([level.start])
    while todo:
        x, y = todo.popleft()
        for nxt in _moves(level, x, y, door_open):
            if nxt not in seen:
                seen.add(nxt)
                todo.append(nxt)
    return seen


def _can_touch(stands: set[tuple[int, int]], x: int, y: int) -> bool:
    return any((x, y + d) in stands for d in range(0, JUMP["rise"] + 1))


def check_playable(level: Level) -> list[str]:
    """Problems that would make the level impossible (empty list = beatable)."""
    problems: list[str] = []
    if not _standable(level, *level.start, door_open=False):
        problems.append("start is not on solid ground")
    if not _standable(level, *level.goal, door_open=True):
        problems.append("goal is not on solid ground")
    keys = [o for o in level.objects if o.kind == KEY]
    first = reachable(level, door_open=False)
    if level.key_door:
        if len(keys) != 1:
            problems.append("a key-and-door level needs exactly one key")
        elif not _can_touch(first, keys[0].x, keys[0].y):
            problems.append("the key can't be reached")
        if level.goal in first:
            problems.append("the goal can be reached without the key")
    after = reachable(level, door_open=True) if level.key_door else first
    if level.goal not in after:
        problems.append("the goal can't be reached")
    if level.boss and not any(o.kind == BOSS for o in level.objects):
        problems.append("boss level has no boss")
    for o in level.objects:
        if not (0 <= o.x < level.width and 0 <= o.y < HEIGHT):
            problems.append(f"{OBJECTS[o.kind]} outside the level")
        elif level.tile(o.x, o.y) in SOLID:
            problems.append(f"{OBJECTS[o.kind]} inside a wall at {o.x},{o.y}")
    if not (0 <= level.start[0] < 4):
        problems.append("start must be in the first 4 columns")
    return problems
