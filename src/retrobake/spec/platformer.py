"""Platformer content generator: resolved game-spec + seed -> engine-neutral levels.

``generate_levels(spec)`` is deterministic: the same spec (including ``seed``) always gives the
same levels. Every level is checked with ``levels.check_playable`` and regenerated with the next
attempt number until it passes, so engines only ever receive beatable levels.

Supported: side-view movement (``side_jump``) with any progression. ``linear_levels`` makes
``world.levels`` stages; ``dungeons_items`` makes ``world.dungeons`` key-and-door stages; and
``open_map`` makes one long stage sized by ``world.map_size``. Top-down movement is M3.
"""

from __future__ import annotations

import random
from typing import Any

from .levels import (
    BLOCK,
    BOSS,
    BUDGETS,
    COIN,
    DOOR,
    EMPTY,
    FILL,
    FLYER,
    GROUND,
    HEART,
    HEIGHT,
    HOPPER,
    KEY,
    LIFE,
    MAX_OBJECTS,
    MAX_SCREENS,
    PLATFORM,
    SCREEN_WIDTH,
    SHOP,
    SPIKES,
    WALKER,
    Level,
    LevelPack,
    Obj,
    check_playable,
)

G_MIN, G_MAX, G_START = 6, 10, 9  # ground surface row range
MAX_ATTEMPTS = 40

_DIFF = {
    # gap widths, enemies per screen, spike-segment weight, seconds of timer per screen
    "easy": {"gaps": (1, 2), "enemies": 1, "spikes": 1, "time": 40},
    "normal": {"gaps": (1, 2), "enemies": 2, "spikes": 2, "time": 30},
    "hard": {"gaps": (2, 3), "enemies": 3, "spikes": 2, "time": 25},
}
_MAP_SCREENS = {"small": 6, "medium": 10, "large": 16}


class UnsupportedSpec(ValueError):
    """The spec asks for something this generator can't make yet. ``message`` is plain English."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def generate_levels(spec: dict[str, Any]) -> LevelPack:
    """All levels for a valid, resolved side-view spec. Raises ``UnsupportedSpec``."""
    from . import validate  # local import: spec/__init__ imports this module's package

    errors = validate(spec)
    if errors:
        raise UnsupportedSpec("The game settings need fixing first: " + errors[0])
    mods = spec["modules"]
    if mods["movement"] != "side_jump":
        raise UnsupportedSpec("Top-down levels aren't ready yet.")
    system = spec["system"]
    prog = mods["progression"]
    world = spec["world"]
    if prog == "linear_levels":
        count, fixed_screens = world["levels"], None
    elif prog == "dungeons_items":
        count, fixed_screens = world["dungeons"], None
    else:
        count, fixed_screens = 1, min(_MAP_SCREENS[world["map_size"]], MAX_SCREENS[system])

    max_screens = MAX_SCREENS[system]
    while True:
        pack = LevelPack(system=system, seed=spec["seed"])
        for i in range(count):
            screens = fixed_screens or _screens_for(i, count, world["difficulty"], max_screens)
            pack.levels.append(_make_level(spec, i, count, min(screens, max_screens)))
        if len(pack.encode()) <= BUDGETS[system] or max_screens <= 2:
            return pack
        max_screens -= 1  # shrink and try again to fit the ROM budget
        fixed_screens = min(fixed_screens, max_screens) if fixed_screens else None


def _screens_for(index: int, count: int, difficulty: str, max_screens: int) -> int:
    bonus = {"easy": -1, "normal": 0, "hard": 1}[difficulty]
    grow = (index * (max_screens - 3)) // max(count, 1)
    return max(3, min(max_screens, 3 + grow + bonus))


def _is_boss_level(spec: dict[str, Any], index: int, count: int) -> bool:
    if "bosses" not in spec["modules"]["extras"]:
        return False
    return index == count - 1 or (count >= 4 and index % 4 == 3)


def _make_level(spec: dict[str, Any], index: int, count: int, screens: int) -> Level:
    for attempt in range(MAX_ATTEMPTS):
        # Deterministic layout from the spec seed; not used for anything secret.
        rng = random.Random((spec["seed"] << 16) | (index << 8) | attempt)  # noqa: S311
        level = _build(spec, index, count, screens, rng)
        if not check_playable(level):
            return level
    return _safe_level(spec, index, count, screens)  # pragma: no cover - plain flat fallback


class _Builder:
    def __init__(self, width: int) -> None:
        self.width = width
        self.tiles = [bytearray(width) for _ in range(HEIGHT)]
        self.ground: list[int | None] = [None] * width  # surface row per column, None = pit
        self.objects: list[Obj] = []

    def column(self, x: int, g: int | None) -> None:
        self.ground[x] = g
        for y in range(HEIGHT):
            self.tiles[y][x] = EMPTY
        if g is not None:
            self.tiles[g][x] = GROUND
            for y in range(g + 1, HEIGHT):
                self.tiles[y][x] = FILL

    def free(self, x: int, y: int) -> bool:
        return (
            0 <= x < self.width
            and 0 <= y < HEIGHT
            and self.tiles[y][x] == EMPTY
            and not any(o.x == x and o.y == y for o in self.objects)
        )

    def add(self, kind: int, x: int, y: int) -> bool:
        if self.free(x, y):
            self.objects.append(Obj(kind, x, y))
            return True
        return False

    def flat(self, x: int, w: int = 1) -> bool:
        """Columns x-w+1..x+w-1 all have the same ground and no hazards."""
        cols = range(x - w + 1, x + w)
        if any(c < 0 or c >= self.width for c in cols):
            return False
        g = self.ground[x]
        return g is not None and all(
            self.ground[c] == g and self.tiles[g][c] == GROUND and self.tiles[g - 1][c] == EMPTY
            for c in cols
        )


def _build(spec: dict[str, Any], index: int, count: int, screens: int, rng: random.Random) -> Level:
    mods = spec["modules"]
    extras = set(mods["extras"])
    diff = _DIFF[spec["world"]["difficulty"]]
    boss = _is_boss_level(spec, index, count)
    key_door = "keys_doors" in extras or mods["progression"] == "dungeons_items"
    width = screens * SCREEN_WIDTH
    b = _Builder(width)

    end_len = SCREEN_WIDTH if boss else 6
    end_start = width - end_len
    g = G_START
    x = 0
    while x < 4:  # safe start
        b.column(x, g)
        x += 1
    platforms: list[tuple[int, int, int]] = []  # (x, row, width)
    gaps: list[tuple[int, int, int]] = []  # (x, width, ground row)
    while x < end_start:
        room = end_start - x
        kind = rng.choices(
            ["flat", "step", "gap", "spikes", "pillar", "platform"],
            weights=[3, 2, 3, diff["spikes"], 2, 2],
        )[0]
        if kind == "step" and room >= 3:
            ng = max(G_MIN, min(G_MAX, g + rng.choice((-2, -1, 1, 2))))
            g = ng
            for _ in range(rng.randint(2, 4)):
                if x < end_start:
                    b.column(x, g)
                    x += 1
        elif kind == "gap" and room >= 6:
            w = rng.randint(*diff["gaps"])
            for _ in range(w):
                b.column(x, None)
                x += 1
            rise = rng.choice((0, 0, -1, 1)) if w <= 2 else 0
            g = max(G_MIN, min(G_MAX, g + rise))
            gaps.append((x - w, w, g))
            for _ in range(3):
                b.column(x, g)
                x += 1
        elif kind == "spikes" and room >= 6:
            w = rng.randint(1, 2)
            for _ in range(2):
                b.column(x, g)
                x += 1
            for _ in range(w):
                b.column(x, g)
                b.tiles[g][x] = SPIKES
                x += 1
            for _ in range(2):
                b.column(x, g)
                x += 1
        elif kind == "pillar" and room >= 5:
            h = rng.randint(1, 2)
            w = rng.randint(1, 2)
            b.column(x, g)
            x += 1
            for _ in range(w):
                b.column(x, g)
                for r in range(g - h, g):
                    b.tiles[r][x] = BLOCK
                x += 1
            for _ in range(2):
                b.column(x, g)
                x += 1
        elif kind == "platform" and room >= 6 and g - 3 >= 1:
            w = rng.randint(3, 4)
            b.column(x, g)
            x += 1
            px = x
            for _ in range(w):
                b.column(x, g)
                b.tiles[g - 2][x] = PLATFORM
                x += 1
            platforms.append((px, g - 2, w))
            b.column(x, g)
            x += 1
        else:
            for _ in range(min(room, rng.randint(2, 4))):
                b.column(x, g)
                x += 1
    while x < width:  # flat end zone / boss arena
        b.column(x, g)
        x += 1

    start = (1, b.ground[1] - 1)
    goal = (width - 2, g - 1)

    # Door: a wall in the end zone the hero can't jump over until the key opens it.
    door_x = end_start + 2
    if key_door:
        for r in range(0, g):
            b.tiles[r][door_x] = DOOR if r >= g - 4 else BLOCK

    # Key: on a platform if possible, else on the ground in the middle third.
    if key_door:
        spots = [(px + w // 2, row - 1) for px, row, w in platforms if px < end_start - 2]
        if not spots:
            spots = [
                (c, b.ground[c] - 1)
                for c in range(width // 3, end_start - 1)
                if b.flat(c) and b.free(c, b.ground[c] - 1)
            ]
        if not spots:
            spots = [(3, b.ground[3] - 1)]
        b.add(KEY, *rng.choice(spots))

    if boss:
        b.add(BOSS, width - 6, g - 1)

    if "shop" in extras and index > 0:
        b.add(SHOP, 2, b.ground[2] - 1)

    _place_enemies(b, mods, diff, screens, end_start, rng)
    _place_pickups(b, spec, index, extras, platforms, gaps, end_start, rng)

    limit = MAX_OBJECTS[spec["system"]]
    if len(b.objects) > limit:  # drop coins first, never key/boss
        keep = [o for o in b.objects if o.kind != COIN]
        coins = [o for o in b.objects if o.kind == COIN]
        b.objects = keep + coins[: max(0, limit - len(keep))]

    time_limit = 0
    if "timer" in extras:
        time_limit = 30 + diff["time"] * screens + (60 if boss else 0)

    return Level(
        index=index,
        width=width,
        tiles=b.tiles,
        objects=sorted(b.objects, key=lambda o: (o.x, o.y, o.kind)),
        start=start,
        goal=goal,
        setting=spec["world"]["setting"],
        boss=boss,
        key_door=key_door,
        time_limit=time_limit,
    )


def _place_enemies(b, mods, diff, screens, end_start, rng) -> None:
    per_screen = diff["enemies"]
    if mods["combat"] == "none":
        per_screen = max(1, per_screen // 2)
    kinds = [WALKER] if mods["combat"] == "none" else [WALKER, HOPPER, FLYER]
    candidates = [c for c in range(8, end_start - 1) if b.flat(c, 2)]
    rng.shuffle(candidates)
    wanted = per_screen * max(1, screens - 1)
    placed: list[int] = []
    for c in candidates:
        if len(placed) >= wanted:
            break
        if any(abs(c - p) < 4 for p in placed):
            continue
        screen = c // SCREEN_WIDTH
        if sum(1 for p in placed if p // SCREEN_WIDTH == screen) >= 3:
            continue  # NES: keep sprites per screen low
        kind = rng.choice(kinds)
        g = b.ground[c]
        y = g - 3 if kind == FLYER else g - 1
        if kind == FLYER and not (b.free(c, y) and b.free(c, y + 1)):
            continue
        if b.add(kind, c, y):
            placed.append(c)


def _place_pickups(b, spec, index, extras, platforms, gaps, end_start, rng) -> None:
    if "collectibles" in extras:
        for px, row, w in platforms:
            for c in range(px, px + w):
                b.add(COIN, c, row - 1)
        for gx, w, g in gaps:
            for c in range(gx, gx + w):
                b.add(COIN, c, g - 3)
        lines = [c for c in range(6, end_start - 3) if b.flat(c, 2)]
        rng.shuffle(lines)
        for c in lines[:3]:
            for d in (-1, 0, 1):
                b.add(COIN, c + d, b.ground[c] - 2)
    ground_spots = [
        (c, b.ground[c] - 1)
        for c in range(6, end_start - 1)
        if b.flat(c) and b.free(c, b.ground[c] - 1)
    ]
    rng.shuffle(ground_spots)
    if "hearts" in extras and ground_spots:
        b.add(HEART, *ground_spots.pop())
    if "lives" in extras and index % 2 == 1:
        high = [(px + w - 1, row - 1) for px, row, w in platforms]
        spot = rng.choice(high) if high else (ground_spots.pop() if ground_spots else None)
        if spot:
            b.add(LIFE, *spot)


def _safe_level(spec: dict[str, Any], index: int, count: int, screens: int) -> Level:
    width = screens * SCREEN_WIDTH
    b = _Builder(width)
    for x in range(width):
        b.column(x, G_START)
    key_door = "keys_doors" in spec["modules"]["extras"] or (
        spec["modules"]["progression"] == "dungeons_items"
    )
    boss = _is_boss_level(spec, index, count)
    end_start = width - (SCREEN_WIDTH if boss else 6)
    if key_door:
        for r in range(0, G_START):
            b.tiles[r][end_start + 2] = DOOR if r >= G_START - 4 else BLOCK
        b.add(KEY, width // 2, G_START - 1)
    if boss:
        b.add(BOSS, width - 6, G_START - 1)
    return Level(
        index=index,
        width=width,
        tiles=b.tiles,
        objects=sorted(b.objects, key=lambda o: (o.x, o.y, o.kind)),
        start=(1, G_START - 1),
        goal=(width - 2, G_START - 1),
        setting=spec["world"]["setting"],
        boss=boss,
        key_door=key_door,
    )
