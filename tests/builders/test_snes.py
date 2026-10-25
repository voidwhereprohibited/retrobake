import os

import pytest

from retrobake import spec as gs
from retrobake.builders import nes_font, snes
from retrobake.builders import snes_font as font

NEED_TOOLS = os.environ.get("RETROBAKE_REQUIRE_WLA") == "1"


def _have_tools() -> bool:
    try:
        snes.find_wladx()
        return True
    except snes.SnesBuildError:
        return False


needs_wla = pytest.mark.skipif(
    not NEED_TOOLS and not _have_tools(), reason="wla-dx not bundled here (CI provides it)"
)


def _spec(title="Hello World", genres=("platformer",)):
    spec, _ = gs.new_spec("snes", list(genres), "a brave fox crosses the hills", title, seed=3)
    return spec


# ---------------------------------------------------------------- pure data


def test_font_is_nes_glyphs_in_snes_2bpp():
    data = font.font_bin()
    assert len(data) == len(font.CHARSET) * 16
    assert data[:16] == bytes(16)  # tile 0 = space = blank
    nes_a = nes_font.chr_bank()[16:32]  # "A"
    assert data[16:32:2] == nes_a[:8]  # plane 0 rows on even bytes
    assert data[17:32:2] == bytes(8)  # plane 1 empty: colour 1 only


def test_text_data_centres_lines_and_terminates():
    data = snes.text_data("HI")
    addr = snes.MAP_VRAM + snes.TITLE_ROW * 32 + 15
    assert data[:5] == bytes([2, addr & 0xFF, addr >> 8]) + font.tiles_for("HI")
    assert data[-1] == 0
    assert data.count(font.tiles_for(snes.PROMPT)) == 1


def test_header_name_and_checksum():
    assert snes.header_name("Fox & Hills: 2!") == b"FOX & HILLS: 2!      "
    assert len(snes.header_name("W" * 40)) == snes.NAME_BYTES
    rom = bytearray(snes.ROM_BYTES)
    rom[0x1234] = 7
    assert snes.checksum(rom) == (7 + 0x1FE) & 0xFFFF


BAD_TITLES = ["", "   ", "Hello`rm -rf`", ".DB $00", "\x00boom", "x" * 200, "Caf\u00e9"]


@pytest.mark.parametrize("bad", BAD_TITLES)
def test_unsafe_titles_never_reach_the_build(bad):
    spec = _spec()
    spec["title"] = bad
    with pytest.raises(snes.SnesBuildError) as err:
        snes.bake(spec, wla_dir="/nonexistent")
    assert err.value.message


def test_rejects_nes_and_broken_specs():
    spec, _ = gs.new_spec("nes", ["platformer"], "x", "Hello", seed=1)
    with pytest.raises(snes.SnesBuildError, match="SNES"):
        snes.bake(spec)
    broken = _spec()
    del broken["modules"]
    with pytest.raises(snes.SnesBuildError, match="settings"):
        snes.bake(broken)


def test_missing_toolchain_is_plain_english(tmp_path, monkeypatch):
    monkeypatch.delenv("RETROBAKE_WLA_DIR", raising=False)
    monkeypatch.setattr(snes, "_app_root", lambda: tmp_path)
    with pytest.raises(snes.SnesBuildError, match="reinstall"):
        snes.find_wladx(tmp_path)


def test_check_rom_rejects_garbage():
    with pytest.raises(snes.SnesBuildError):
        snes.check_rom(bytes(snes.ROM_BYTES))
    with pytest.raises(snes.SnesBuildError):
        snes.check_rom(b"\x00" * 100)


# ---------------------------------------------------------------- real bake (CI)
# Boot + Start -> gameplay is checked on the Snes9x libretro core by qa's smoke test
# (CI job snes-bake runs tests/emulator/run_smoke.py on the baked sample ROM).


@needs_wla
def test_bake_hello_world_rom_is_valid_lorom_with_title_data():
    result = snes.bake(_spec("Fox & Hills: 2!"))
    rom = result.rom
    assert len(rom) == snes.ROM_BYTES and result.mapper == "LoROM"
    snes.check_rom(rom)
    assert rom[snes.HEADER : snes.HEADER + 21] == snes.header_name("Fox & Hills: 2!")
    assert snes.text_data("Fox & Hills: 2!") in rom
    assert font.font_bin() in rom
    assert rom[0x7FFC:0x7FFE] == b"\x00\x80"  # reset -> $8000


@needs_wla
def test_bake_is_deterministic_and_works_for_mashups():
    a = snes.bake(_spec("Same Game")).rom
    b = snes.bake(_spec("Same Game")).rom
    assert a == b
    mash = snes.bake(_spec("Mashup", ("platformer", "topdown_adventure")))
    assert mash.engine == "hello"
