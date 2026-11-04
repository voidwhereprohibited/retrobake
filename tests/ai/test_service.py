# ruff: noqa: S101, PLR2004 - pytest asserts and literal limits are the point of tests
import pytest

from retrobake.ai import AIService, CoverArt, cover_size, parse_names
from retrobake.ai.raster import from_png
from retrobake.security import InputRejected, find_ip
from retrobake.spec import new_spec


def spec(system="nes"):
    s, _ = new_spec(system, "platformer", "a frog who saves the moon", seed=42)
    return s


@pytest.mark.parametrize("system", ["nes", "snes"])
def test_art_is_offline_at_box_size(system):
    art = AIService().make_art(spec(system))
    assert art.source == "offline" and art.message == ""
    img = from_png(art.png)
    assert (img.width, img.height) == cover_size(spec(system)) == (art.width, art.height)


def test_art_is_deterministic_and_variants_differ():
    ai = AIService()
    assert ai.make_art(spec()).png == ai.make_art(spec()).png
    assert ai.make_art(spec(), variant=1).png != ai.make_art(spec()).png


@pytest.mark.parametrize("n", [1, 5, 6, 12])
def test_names_are_offline_and_clean(n):
    ideas = AIService().suggest_names(spec(), n)
    assert ideas.source == "offline" and len(ideas.names) == n
    assert all(not find_ip(x) and len(x) <= 24 for x in ideas.names)
    assert len({x.casefold() for x in ideas.names}) == n


def test_parse_names_filters_and_handles_non_lists():
    lines = ["1. Moon Frog Rescue", "2) Super Mario Moon", "- Lily Pad Leap", "x" * 80]
    assert parse_names(lines) == ["Moon Frog Rescue", "Lily Pad Leap"]
    assert parse_names(None) == [] and parse_names({"a": 1}) == []
    assert parse_names(["ok name", 5, None]) == ["ok name"]


def test_with_title_banner():
    art = AIService().make_art(spec("snes"))
    final = AIService.with_title(art, "Moon Frog")
    img = from_png(final)
    assert (img.width, img.height) == (art.width, art.height) and final != art.png
    assert isinstance(art, CoverArt)


@pytest.mark.parametrize("title", ["Super Mario Frog", "", "   ", "bad<title>"])
def test_with_title_rejects_bad_titles(title):
    art = AIService().make_art(spec())
    with pytest.raises(InputRejected):
        AIService.with_title(art, title)


def test_cover_convenience():
    png, art = AIService().cover(spec(), "Moon Frog", variant=2)
    assert from_png(png).width == art.width
