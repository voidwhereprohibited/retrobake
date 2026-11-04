import itertools

import pytest

from retrobake.ai import COVER_SIZE, offline_art, offline_names
from retrobake.ai.font import CHARSET, add_title_banner
from retrobake.ai.offline import _MOODS, _NAMES, _SETTINGS
from retrobake.ai.raster import Canvas, from_png
from retrobake.security import check_title, find_ip
from retrobake.spec import catalog

ARCHETYPES = sorted(catalog()["hero_archetypes"])


def spec(**kw):
    s = {
        "system": "nes",
        "genres": ["platformer"],
        "world": {"setting": "grassland"},
        "style": {"palette_mood": "bright"},
        "hero": {"archetype": "knight"},
        "seed": 1234,
    }
    for k, v in kw.items():
        if isinstance(v, dict):
            s[k] = {**s.get(k, {}), **v}
        else:
            s[k] = v
    return s


def test_sizes_match_box_shape():
    assert (offline_art(spec()).width, offline_art(spec()).height) == COVER_SIZE["nes"]
    snes = offline_art(spec(system="snes"))
    assert (snes.width, snes.height) == COVER_SIZE["snes"]


def test_deterministic_and_variants_differ():
    a = offline_art(spec()).to_png()
    assert a == offline_art(spec()).to_png()
    assert a != offline_art(spec(), variant=1).to_png()
    assert a != offline_art(spec(seed=99)).to_png()


@pytest.mark.parametrize(
    "setting,mood", list(itertools.product(sorted(_SETTINGS), sorted(_MOODS)))[::5]
)
def test_every_setting_and_mood_renders(setting, mood):
    img = offline_art(spec(world={"setting": setting}, style={"palette_mood": mood}))
    assert len(set(bytes(img.data[i : i + 3]) for i in range(0, len(img.data), 3 * 97))) > 4


@pytest.mark.parametrize("arch", ARCHETYPES)
@pytest.mark.parametrize("genre", ["platformer", "shooter", "puzzle", "sports", "rpg"])
def test_every_hero_and_genre_renders(arch, genre):
    offline_art(spec(hero={"archetype": arch}, genres=[genre]))


def test_garbage_spec_still_renders():
    for bad in ({}, {"system": "x", "world": "nope", "seed": "a", "genres": None}):
        img = offline_art(bad)
        assert (img.width, img.height) == COVER_SIZE["nes"]


def test_png_roundtrip():
    img = offline_art(spec(system="snes"))
    back = from_png(img.to_png())
    assert (back.width, back.height, back.data) == (img.width, img.height, img.data)


def test_from_png_rejects_junk():
    for junk in (b"", b"GIF89a", b"\x89PNG\r\n\x1a\n" + b"\x00" * 30):
        with pytest.raises(ValueError):
            from_png(junk)


def test_title_banner_draws_and_keeps_size():
    c = Canvas(512, 704, (40, 80, 160))
    before = bytes(c.data)
    add_title_banner(c, "Frost Dash Of The North", bg=(0, 0, 0), fg=(255, 255, 0), shadow=(0, 0, 0))
    assert (c.width, c.height) == (512, 704) and bytes(c.data) != before
    assert (255, 255, 0) in {c.get(x, y) for x in range(0, 512, 3) for y in range(0, 200, 3)}


def test_font_covers_title_charset():
    for ch in "ABCXYZ0129.,!?'&:- abc":
        assert ch in CHARSET


@pytest.mark.parametrize("arch", ARCHETYPES)
@pytest.mark.parametrize("setting", sorted(_SETTINGS))
def test_names_valid_original_and_deterministic(arch, setting):
    s = spec(hero={"archetype": arch}, world={"setting": setting}, genres=["rpg"])
    names = offline_names(s, 8)
    assert len(names) == 8 and len({n.casefold() for n in names}) == 8
    assert names == offline_names(s, 8)
    for n in names:
        assert check_title(n) == n and len(n) <= 24 and not find_ip(n)


def test_names_count_bounds_and_garbage_spec():
    assert len(offline_names({}, 1)) == 1
    assert len(offline_names({"genres": [1, None]}, 50)) == 12


# --- no mashed-up names -------------------------------------------------------------


@pytest.mark.parametrize("setting", sorted(_SETTINGS))
def test_names_come_only_from_the_settings_curated_list(setting):
    assert len(_NAMES[setting]) >= 12
    for variant in range(5):
        for genre in ("platformer", "topdown_adventure", "rpg"):
            s = spec(world={"setting": setting}, genres=[genre], seed=variant)
            assert set(offline_names(s, 12, variant=variant)) <= set(_NAMES[setting])


def test_names_ignore_genre_and_hero():
    base = offline_names(spec(), 6)
    assert offline_names(spec(genres=["rpg"], hero={"archetype": "robot"}), 6) == base


def test_curated_lists_are_single_theme_and_not_templated():
    every = [n for names in _NAMES.values() for n in names]
    assert len(every) == len({n.casefold() for n in every})  # no title shared between settings
    assert set(_NAMES) == set(_SETTINGS)
    for name in every:
        assert not name.startswith("Super ") and not name.endswith(" II")
        assert check_title(name) == name and not find_ip(name)
