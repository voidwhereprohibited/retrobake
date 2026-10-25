import os

import pytest
from mini6502 import Machine

from retrobake import spec as gs
from retrobake.builders import nes
from retrobake.builders import nes_font as font

NEED_TOOLS = os.environ.get("RETROBAKE_REQUIRE_CC65") == "1"


def _have_tools() -> bool:
    try:
        nes.find_cc65()
        return True
    except nes.NesBuildError:
        return False


needs_cc65 = pytest.mark.skipif(
    not NEED_TOOLS and not _have_tools(), reason="cc65 not bundled here (CI provides it)"
)


def _spec(title="Hello World", genres=("platformer",)):
    spec, _ = gs.new_spec("nes", list(genres), "a brave fox crosses the hills", title, seed=3)
    return spec


# ---------------------------------------------------------------- pure data


def test_font_covers_spec_charset_and_fits_one_bank():
    bank = font.chr_bank()
    assert len(bank) == 8192
    assert bank[:16] == bytes(16)  # tile 0 = space = blank
    allowed = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 .,!?'&:-"
    assert len(font.tiles_for(allowed)) == len(allowed)
    assert font.tiles_for("a") == font.tiles_for("A")
    with pytest.raises(ValueError):
        font.tiles_for("~")


def test_text_data_centres_lines_and_terminates():
    data = nes.text_data("HI")
    addr = 0x2000 + nes.TITLE_ROW * 32 + 15
    assert data[:5] == bytes([addr >> 8, addr & 0xFF, 2]) + font.tiles_for("HI")
    assert data[-1] == 0
    assert len(nes.text_data("W" * 24)) < 256


@pytest.mark.parametrize(
    "bad", ["", "   ", "Hello`rm -rf`", ".jsr $C000", "\x00boom", "x" * 200]
)
def test_unsafe_titles_never_reach_the_build(bad):
    spec = _spec()
    spec["title"] = bad
    with pytest.raises(nes.NesBuildError) as err:
        nes.bake(spec, cc65_dir="/nonexistent")
    assert err.value.message  # plain English for the UI


def test_rejects_snes_and_broken_specs():
    spec, _ = gs.new_spec("snes", ["platformer"], "x", "Hello", seed=1)
    with pytest.raises(nes.NesBuildError, match="NES"):
        nes.bake(spec)
    broken = _spec()
    del broken["modules"]
    with pytest.raises(nes.NesBuildError, match="settings"):
        nes.bake(broken)


def test_missing_toolchain_is_plain_english(tmp_path):
    with pytest.raises(nes.NesBuildError, match="reinstall"):
        nes.find_cc65(tmp_path)


def test_check_rom_rejects_garbage():
    with pytest.raises(nes.NesBuildError):
        nes.check_rom(b"NES\x1a" + bytes(100))


# ---------------------------------------------------------------- real bake (CI)


@needs_cc65
def test_bake_hello_world_rom_boots_and_shows_title():
    result = nes.bake(_spec("Fox & Hills: 2!"))
    rom = result.rom
    assert len(rom) == nes.ROM_BYTES and rom[:4] == b"NES\x1a"
    assert rom[-8192:] == font.chr_bank()

    m = Machine(rom)
    m.run_until_idle()
    title = font.tiles_for("Fox & Hills: 2!")
    start = 0x2000 + nes.TITLE_ROW * 32 + (32 - len(title)) // 2
    assert bytes(m.vram[start : start + len(title)]) == title
    credit = font.tiles_for(nes.CREDIT)
    cstart = 0x2000 + nes.CREDIT_ROW * 32 + (32 - len(credit)) // 2
    assert bytes(m.vram[cstart : cstart + len(credit)]) == credit
    assert m.vram[0x3F00] == 0x0F and m.vram[0x3F01] == 0x30
    assert m.ppumask == 0x0A  # background on


@needs_cc65
def test_bake_is_deterministic_and_works_for_mashups():
    a = nes.bake(_spec("Same Game")).rom
    b = nes.bake(_spec("Same Game")).rom
    assert a == b
    mash = nes.bake(_spec("Mashup", ("platformer", "topdown_adventure")))
    assert mash.mapper == "NROM-128"
