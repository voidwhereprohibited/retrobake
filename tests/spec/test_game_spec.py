import itertools
import json
from pathlib import Path

import pytest

from retrobake import spec as gs
from retrobake.spec.catalog import catalog, schema

SYSTEMS = ["nes", "snes"]
ALL_GENRES = list(catalog()["genres"])
AVAILABLE = gs.available_genres()


def _enum(*path):
    node = schema()["properties"]
    for p in path:
        node = node[p]
    return node["enum"] if "enum" in node else node["items"]["enum"]


def test_schema_enums_match_catalog():
    cat = catalog()
    assert _enum("system") == list(cat["systems"])
    assert _enum("genres") == list(cat["genres"])
    for kind in ("movement", "combat", "progression"):
        assert schema()["properties"]["modules"]["properties"][kind]["enum"] == list(
            cat["modules"][kind]
        )
    assert schema()["properties"]["modules"]["properties"]["extras"]["items"]["enum"] == list(
        cat["modules"]["extras"]
    )
    world = schema()["properties"]["world"]["properties"]
    assert world["setting"]["enum"] == list(cat["settings"])
    assert world["difficulty"]["enum"] == list(cat["difficulties"])
    assert world["map_size"]["enum"] == list(cat["map_sizes"])
    style = schema()["properties"]["style"]["properties"]
    assert style["palette_mood"]["enum"] == list(cat["palette_moods"])
    assert style["music_mood"]["enum"] == list(cat["music_moods"])
    assert schema()["properties"]["hero"]["properties"]["archetype"]["enum"] == list(
        cat["hero_archetypes"]
    )
    assert sorted(cat["extras_priority"]) == sorted(cat["modules"]["extras"])


def test_day_one_genres():
    assert AVAILABLE == ["platformer", "topdown_adventure"]


@pytest.mark.parametrize("system", SYSTEMS)
@pytest.mark.parametrize(
    "genres", [[g] for g in AVAILABLE] + [list(p) for p in itertools.permutations(AVAILABLE, 2)]
)
def test_new_spec_is_valid(system, genres):
    spec, _ = gs.new_spec(system, genres, "a hero saves the valley", seed=7)
    assert gs.validate(spec) == []
    json.dumps(spec)  # must be plain JSON


@pytest.mark.parametrize("system", SYSTEMS)
def test_every_module_combination_resolves_to_valid(system):
    cat = catalog()["modules"]
    for mv, cb, pr in itertools.product(cat["movement"], cat["combat"], cat["progression"]):
        for n in range(0, 9, 2):
            extras = list(cat["extras"])[:n]
            spec, _ = gs.new_spec(system, ["platformer"], seed=1)
            spec["modules"] = {"movement": mv, "combat": cb, "progression": pr, "extras": extras}
            spec["world"].update(levels=16, dungeons=8, map_size="large")
            fixed, _ = gs.resolve(spec)
            assert gs.validate(fixed) == [], (mv, cb, pr, extras)
            assert gs.resolve(fixed)[1] == []  # resolve is idempotent


def test_platformer_topdown_mashup_matches_plan():
    spec, _ = gs.new_spec("nes", ["platformer", "topdown_adventure"], seed=1)
    m = spec["modules"]
    assert (m["movement"], m["combat"], m["progression"]) == (
        "side_jump",
        "melee",
        "dungeons_items",
    )
    assert "hearts" in m["extras"]


def test_resolve_examples():
    spec, _ = gs.new_spec("nes", ["topdown_adventure"], seed=1)
    spec["modules"].update(combat="stomp", extras=["shop", "timer"])
    fixed, fixes = gs.resolve(spec)
    rules = {f.rule for f in fixes}
    assert fixed["modules"]["combat"] == "melee"
    assert {
        "stomp_needs_jump",
        "shop_needs_collectibles",
        "timer_only_in_stages",
        "need_fail_state",
    } <= rules
    assert rules <= set(gs.INCOMPATIBLE)
    assert spec["modules"]["combat"] == "stomp"  # input not mutated


def test_nes_limits():
    spec, _ = gs.new_spec("nes", ["platformer"], seed=1)
    spec["world"]["levels"] = 16
    spec["modules"]["extras"] = list(catalog()["modules"]["extras"])
    assert gs.validate(spec)
    fixed, _ = gs.resolve(spec)
    assert fixed["world"]["levels"] == 8 and len(fixed["modules"]["extras"]) == 5
    assert gs.validate(fixed) == []


@pytest.mark.parametrize(
    "bad",
    [
        {"title": ""},
        {"title": "x" * 25},
        {"title": "Bad\x00Title"},
        {"title": "$(rm -rf ~)"},
        {"description": "hi\x1b[31m"},
        {"system": "genesis"},
        {"genres": []},
        {"genres": ["platformer", "platformer"]},
        {"genres": ["platformer", "shooter", "rpg"]},
        {"seed": -1},
        {"evil": 1},
    ],
)
def test_rejects_bad_specs(bad):
    spec, _ = gs.new_spec("snes", ["platformer"], seed=1)
    spec.update(bad)
    assert gs.validate(spec)


def test_unavailable_genre_rejected():
    spec, _ = gs.new_spec("snes", ["platformer"], seed=1)
    spec["genres"] = ["shooter"]
    assert any("not available" in e for e in gs.validate(spec))


def test_questions_and_answers_flow():
    spec, _ = gs.new_spec("nes", ["platformer", "topdown_adventure"], seed=1)
    qs = gs.questions_for(spec)
    ids = [q["id"] for q in qs]
    assert ids[:2] == ["feel", "world_shape"]
    assert "dungeons" in ids and "levels" not in ids
    for q in qs:
        assert q["prompt"] and q["default"] is not None or q["kind"] == "text"
        if q["kind"] in ("choice", "multi"):
            assert q["options"]
    combat = next(q for q in qs if q["id"] == "combat")
    assert "stomp" in {o["value"] for o in combat["options"]}

    spec, _ = gs.apply_answers(spec, {"world_shape": "linear_levels"})
    spec, _ = gs.apply_answers(spec, {"levels": 6, "difficulty": "hard", "bogus": 1})
    assert spec["world"]["levels"] == 6 and spec["world"]["difficulty"] == "hard"
    spec, _ = gs.apply_answers(spec, {"feel": "topdown_adventure"})
    assert spec["genres"][0] == "topdown_adventure"
    assert spec["modules"]["movement"] == "topdown_walk"
    combat = next(q for q in gs.questions_for(spec) if q["id"] == "combat")
    assert "stomp" not in {o["value"] for o in combat["options"]}
    assert gs.validate(spec) == []


def test_franchise_refs_become_style_only():
    text = "Like Zelda meets MARIO, with a bit of mega man"
    hints = gs.style_from_text(text)
    assert hints.genres == ["topdown_adventure", "platformer"]
    assert hints.matched == 3
    low = hints.clean_text.lower()
    assert "zelda" not in low and "mario" not in low and "mega man" not in low
    assert set(hints.tags) <= gs.STYLE_TAGS
    assert gs.style_from_text("marionette armario").matched == 0  # whole words only

    spec, _ = gs.new_spec("snes", ["platformer"], "a game like metroid", seed=1)
    assert spec["modules"]["progression"] == "open_map"
    assert "metroid" not in json.dumps(spec).lower()
    assert gs.validate(spec) == []


def test_schema_file_is_valid_draft7():
    import fastjsonschema

    path = Path(gs.__file__).with_name("game_spec.schema.json")
    fastjsonschema.compile(json.loads(path.read_text(encoding="utf-8")))


def test_docs_list_every_rule():
    doc = Path(__file__).resolve().parents[2] / "docs" / "game-spec.md"
    text = doc.read_text(encoding="utf-8")
    for rule in gs.INCOMPATIBLE:
        assert f"`{rule}`" in text
