# ruff: noqa: S311 - seeded, reproducible fuzz data; not used for security
"""Property tests for the platformer level generator (owner: qa).

Independent of game-design's own tests: random specs across every system, progression,
difficulty, map size, level/dungeon count, extras subset and the full seed range. Every pack
must be deterministic, fit its ROM budget, survive a binary round trip, stay inside the
grid and object limits engines rely on, and every level must be beatable.
"""

from __future__ import annotations

import os
import random
import struct
import time

import pytest

from retrobake import spec as gs
from retrobake.spec import levels as lv
from retrobake.spec.platformer import UnsupportedSpec, generate_levels

N = int(os.environ.get("RETROBAKE_FUZZ_N", "300")) // 2
EXTRAS = ["hearts", "lives", "collectibles", "bosses", "keys_doors", "score", "timer", "shop"]
SLOW = 3.0


def random_spec(rng: random.Random) -> dict:
    system = rng.choice(["nes", "snes"])
    seed = rng.choice([0, 1, 2**32 - 1, rng.randrange(2**32)])
    spec, _ = gs.new_spec(system, ["platformer"], seed=seed)
    spec["modules"]["progression"] = rng.choice(["linear_levels", "open_map", "dungeons_items"])
    spec["modules"]["extras"] = rng.sample(EXTRAS, rng.randint(0, len(EXTRAS)))
    spec["world"]["difficulty"] = rng.choice(["easy", "normal", "hard"])
    spec["world"]["map_size"] = rng.choice(["small", "medium", "large"])
    spec["world"]["levels"] = rng.randint(1, 16)
    spec["world"]["dungeons"] = rng.randint(1, 8)
    spec, _ = gs.resolve(spec)
    return spec


def check_level(level: lv.Level, system: str) -> None:
    assert lv.check_playable(level) == [], level.index
    assert 1 <= level.screens <= lv.MAX_SCREENS[system]
    assert level.width == level.screens * lv.SCREEN_WIDTH <= 256
    assert len(level.tiles) == lv.HEIGHT
    assert all(len(row) == level.width and max(row) <= lv.DECOR for row in level.tiles)
    assert len(level.objects) <= lv.MAX_OBJECTS[system]
    for o in level.objects:
        assert o.kind in lv.OBJECTS
        assert 0 <= o.x < level.width and 0 <= o.y < lv.HEIGHT, (o.kind, o.x, o.y)
    for x, y in (level.start, level.goal):
        assert 0 <= x < level.width and 0 <= y < lv.HEIGHT
    assert 0 <= level.time_limit < 65536
    per_screen: dict[int, int] = {}
    for o in level.objects:
        if o.kind in (lv.WALKER, lv.HOPPER, lv.FLYER):
            per_screen[o.x // lv.SCREEN_WIDTH] = per_screen.get(o.x // lv.SCREEN_WIDTH, 0) + 1
    assert max(per_screen.values(), default=0) <= 3


def test_random_specs_always_give_good_packs():
    rng = random.Random(31)
    made = 0
    for _ in range(N):
        spec = random_spec(rng)
        start = time.perf_counter()
        try:
            pack = generate_levels(spec)
        except UnsupportedSpec as exc:
            assert exc.message
            continue
        assert time.perf_counter() - start < SLOW
        made += 1
        system = spec["system"]
        blob = pack.encode()
        assert len(blob) <= lv.BUDGETS[system], (system, len(blob))
        assert generate_levels(spec).encode() == blob, "must be deterministic"
        assert lv.decode_pack(blob).encode() == blob, "binary round trip"
        prog = spec["modules"]["progression"]
        world = spec["world"]
        want = {"linear_levels": world.get("levels"), "dungeons_items": world.get("dungeons")}
        assert len(pack.levels) == want.get(prog, 1)
        for level in pack.levels:
            check_level(level, system)
    assert made > N // 2, f"only {made}/{N} random specs produced levels"


@pytest.mark.parametrize("system", ["nes", "snes"])
def test_biggest_worlds_fit_the_budget(system):
    for prog in ("linear_levels", "open_map", "dungeons_items"):
        for seed in (0, 7, 2**32 - 1):
            spec, _ = gs.new_spec(system, ["platformer"], seed=seed)
            spec["modules"]["progression"] = prog
            spec["modules"]["extras"] = list(EXTRAS)
            spec["world"].update(difficulty="hard", map_size="large", levels=16, dungeons=8)
            spec, _ = gs.resolve(spec)
            pack = generate_levels(spec)
            assert len(pack.encode()) <= lv.BUDGETS[system]
            for level in pack.levels:
                check_level(level, system)


def test_level_decoder_rejects_junk_cleanly():
    rng = random.Random(32)
    good = generate_levels(random_spec(random.Random(1))).encode()
    samples = [b"", b"RBLV", good[:7], good[:-1], b"RBLV\x09" + good[5:]]
    for _ in range(300):
        blob = bytearray(good)
        for _ in range(rng.randint(1, 8)):
            blob[rng.randrange(len(blob))] = rng.getrandbits(8)
        samples.append(bytes(blob))
    samples += [bytes(rng.getrandbits(8) for _ in range(rng.randint(0, 200))) for _ in range(200)]
    for data in samples:
        start = time.perf_counter()
        try:
            lv.decode_pack(data)  # reference decoder (tests/tools only): any plain error is ok
        except (ValueError, IndexError, KeyError, struct.error):
            pass
        assert time.perf_counter() - start < SLOW
