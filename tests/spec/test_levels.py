import itertools
import json
from collections import Counter

import pytest

from retrobake import spec as gs
from retrobake.spec import levels as lv
from retrobake.spec.platformer import UnsupportedSpec, generate_levels


def _spec(system="nes", genres=("platformer",), seed=1, **answers):
    spec, _ = gs.new_spec(system, list(genres), seed=seed)
    if answers:
        spec, _ = gs.apply_answers(spec, answers)
    assert gs.validate(spec) == []
    return spec


EXTRAS_SETS = [
    [],
    ["lives", "collectibles", "bosses"],
    ["hearts", "keys_doors", "bosses", "collectibles", "timer"],
    ["lives", "shop", "collectibles", "score"],
]


@pytest.mark.parametrize("system", ["nes", "snes"])
@pytest.mark.parametrize("difficulty", ["easy", "normal", "hard"])
@pytest.mark.parametrize("extras", range(len(EXTRAS_SETS)))
def test_levels_are_beatable_and_fit(system, difficulty, extras):
    for seed in range(4):
        n = 8 if system == "nes" else 16
        spec = _spec(system, seed=seed, difficulty=difficulty, levels=n)
        spec["modules"]["extras"] = EXTRAS_SETS[extras]
        spec, _ = gs.resolve(spec)
        pack = generate_levels(spec)
        assert len(pack.levels) == n
        assert len(pack.encode()) <= lv.BUDGETS[system]
        for level in pack.levels:
            assert lv.check_playable(level) == [], (seed, level.index)
            assert level.screens <= lv.MAX_SCREENS[system]
            assert len(level.objects) <= lv.MAX_OBJECTS[system]
            per_screen = Counter(
                o.x // lv.SCREEN_WIDTH
                for o in level.objects
                if o.kind in (lv.WALKER, lv.HOPPER, lv.FLYER)
            )
            assert max(per_screen.values(), default=0) <= 3
            extras_set = set(spec["modules"]["extras"])
            assert level.key_door == ("keys_doors" in extras_set)
            assert (level.time_limit > 0) == ("timer" in extras_set)
            kinds = {o.kind for o in level.objects}
            if "collectibles" not in extras_set:
                assert lv.COIN not in kinds
            if spec["modules"]["combat"] == "none":
                assert not kinds & {lv.HOPPER, lv.FLYER}
        assert pack.levels[-1].boss == ("bosses" in spec["modules"]["extras"])


def test_deterministic_and_seed_sensitive():
    a = generate_levels(_spec(seed=42)).encode()
    assert a == generate_levels(_spec(seed=42)).encode()
    assert a != generate_levels(_spec(seed=43)).encode()


def test_binary_round_trip():
    spec = _spec("snes", seed=9, levels=10)
    spec["modules"]["extras"] = ["hearts", "keys_doors", "bosses", "collectibles", "timer"]
    pack = generate_levels(spec)
    back = lv.decode_pack(pack.encode())
    assert back.system == "snes" and len(back.levels) == 10
    for a, b in zip(pack.levels, back.levels, strict=True):
        assert a.to_dict() == b.to_dict()


def test_json_shape():
    d = generate_levels(_spec()).to_dict()
    json.dumps(d)
    assert d["format"] == "retrobake-levels" and d["height"] == lv.HEIGHT
    level = d["levels"][0]
    assert len(level["rows"]) == lv.HEIGHT
    assert all(len(r) == level["width"] for r in level["rows"])
    assert level["width"] % lv.SCREEN_WIDTH == 0


@pytest.mark.parametrize(
    ("genres", "answers", "expect"),
    [
        (("platformer", "topdown_adventure"), {"dungeons": 4}, 4),
        (("platformer",), {"world_shape": "open_map"}, 1),
    ],
)
def test_other_progressions(genres, answers, expect):
    spec = _spec("snes", genres, seed=3)
    if "world_shape" in answers:
        spec["modules"]["progression"] = "open_map"
        spec["world"]["map_size"] = "large"
        spec, _ = gs.resolve(spec)
    else:
        spec, _ = gs.apply_answers(spec, answers)
    pack = generate_levels(spec)
    assert len(pack.levels) == expect
    for level in pack.levels:
        assert lv.check_playable(level) == []
        if spec["modules"]["progression"] == "dungeons_items":
            assert level.key_door


def test_topdown_not_supported_yet():
    with pytest.raises(UnsupportedSpec) as exc:
        generate_levels(_spec("nes", ("topdown_adventure",)))
    assert "Top-down" in exc.value.message


def test_invalid_spec_rejected():
    spec = _spec()
    spec["title"] = ""
    with pytest.raises(UnsupportedSpec):
        generate_levels(spec)


def test_checker_catches_impossible_levels():
    level = generate_levels(_spec(seed=5)).levels[0]
    for y in range(lv.HEIGHT):  # cut a 6-wide pit in the middle
        for x in range(20, 26):
            level.tiles[y][x] = lv.EMPTY
    assert "the goal can't be reached" in lv.check_playable(level)


def test_ip_guard_in_validate():
    spec = _spec()
    spec["title"] = "Super Mario Quest"
    assert any(e.startswith("title:") for e in gs.validate(spec))
    spec = _spec()
    spec["description"] = "a hero like Link from Hyrule"
    assert any(e.startswith("description:") for e in gs.validate(spec))
    assert "Hyrule" not in gs.scrub_text("a hero like Link from Hyrule")


def test_new_spec_and_answers_scrub_free_text():
    spec, _ = gs.new_spec("nes", ["platformer"], "my hero is like Samus Aran", seed=1)
    assert "Samus" not in spec["description"]
    spec, _ = gs.apply_answers(spec, {"hero_description": "a plumber like Mario"})
    assert "Mario" not in spec["hero"]["description"]
    assert gs.validate(spec) == []


def test_sweep_many_seeds_quickly():
    for seed, (system, diff) in itertools.product(
        range(40), itertools.product(["nes", "snes"], ["easy", "hard"])
    ):
        pack = generate_levels(_spec(system, seed=seed, difficulty=diff, levels=4))
        assert all(lv.check_playable(level) == [] for level in pack.levels)
