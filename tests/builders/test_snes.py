import os

import pytest

from retrobake import spec as gs
from retrobake.builders import nes_font, snes
from retrobake.builders import snes_font as font
from retrobake.builders import snes_gfx as gfx
from retrobake.spec.levels import decode_pack

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


def test_engine_choice_follows_movement():
    assert snes.engine_for(_spec()) == "platformer"
    assert snes.engine_for(_spec(genres=("topdown_adventure",))) == "hello"


def test_config_bytes_come_only_from_enums():
    spec = _spec()
    spec["modules"]["combat"] = "projectile"
    spec["modules"]["extras"] = ["hearts", "lives", "score", "timer", "bosses"]
    cfg = snes.config_data(spec)
    assert len(cfg) == snes.CONFIG_BYTES
    assert cfg[0] == snes.COMBAT_IDS["projectile"]
    assert cfg[1] == 1 | 2 | 8 | 16
    assert cfg[2] == snes.START_LIVES and cfg[3] == snes.START_HEARTS
    spec["modules"]["extras"] = []
    assert snes.config_data(spec)[1:4] == bytes([0, 0, 1])


def test_platformer_title_text_uses_bg3_offsets():
    data = snes.text_data("HI", "platformer")
    off = snes.P_TITLE_ROW * 32 + 15
    assert data[:5] == bytes([2, off & 0xFF, off >> 8]) + font.tiles_for("HI")
    assert data[-1] == 0


def test_level_pack_is_the_level_data_contract():
    spec = _spec()
    blob = snes.level_data(spec)
    pack = decode_pack(blob)
    assert pack.system == "snes" and len(pack.levels) == spec["world"]["levels"]
    assert len(blob) <= 32768  # one LoROM bank


def test_data_files_have_fixed_sizes():
    spec = _spec()
    files = snes.data_files(spec, "HELLO", "platformer")
    sizes = {"objtiles.bin": 8192, "objpal.bin": 256, "hudpal.bin": 64, "ascii.bin": 128}
    sizes.update({"bg2map.bin": 8192, "settings.bin": 12 * gfx.SETTING_BYTES, "config.bin": 16})
    for name, size in sizes.items():
        assert len(files[name]) == size, name
    assert len(files["hudtiles.bin"]) == (len(font.CHARSET) + len(gfx.ICONS)) * 16
    for arch in gfx.HEADS:
        assert len(gfx.obj_tiles(arch)) == 8192
    for mood in gfx.MOODS:
        assert len(gfx.settings_bin(mood)) == 12 * gfx.SETTING_BYTES


def test_settings_order_matches_the_catalog():
    assert len(gfx.SETTINGS) == len(gs.catalog()["settings"]) == 12
    blob = gfx.settings_bin("bright")
    variants = [blob[i * gfx.SETTING_BYTES + gfx.SETTING_OFFSETS["variant"]] for i in range(12)]
    assert set(variants) <= {0, 1, 2, 3}
    assert variants[list(gs.catalog()["settings"]).index("city")] == 2


def test_ascii_table_maps_engine_messages():
    table = gfx.ascii_table()
    for ch in "STAGE CLEAR! GAME OVER - 10: YOU WIN":
        assert table[ord(ch)] == font.CHARSET.index(ch)


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
def test_bake_platformer_rom_is_valid_lorom_with_spec_data():
    spec = _spec("Fox & Hills: 2!")
    result = snes.bake(spec)
    rom = result.rom
    assert result.engine == "platformer" and result.mapper == "LoROM"
    assert len(rom) == snes.ROM_SIZES["platformer"] == 128 * 1024
    snes.check_rom(rom, len(rom))
    assert rom[snes.HEADER : snes.HEADER + 21] == snes.header_name("Fox & Hills: 2!")
    assert rom[snes.HEADER + 0x17] == 0x07  # 128 KB
    assert snes.text_data("Fox & Hills: 2!", "platformer") in rom
    assert rom[0x8000 : 0x8000 + len(snes.level_data(spec))] == snes.level_data(spec)  # bank 1
    assert rom[0x10000:0x12000] == gfx.obj_tiles(spec["hero"]["archetype"])  # bank 2
    assert rom[0x18000 : 0x18000 + len(gfx.settings_bin("bright"))] == gfx.settings_bin(
        spec["style"]["palette_mood"]
    )
    assert rom[0x7FFC:0x7FFE] == b"\x00\x80"  # reset -> $8000


@needs_wla
def test_bake_is_deterministic_and_every_option_bakes():
    a = snes.bake(_spec("Same Game")).rom
    b = snes.bake(_spec("Same Game")).rom
    assert a == b
    mash = snes.bake(_spec("Mashup", ("platformer", "topdown_adventure")))
    assert mash.engine == "platformer"  # side view + sword + dungeons
    for combat in snes.COMBAT_IDS:
        spec = _spec("Combat Test")
        spec["modules"]["combat"] = combat
        if combat == "none":  # spec rule: bosses need a way to fight
            spec["modules"]["extras"].remove("bosses")
        assert len(snes.bake(spec).rom) == 128 * 1024


@needs_wla
def test_topdown_specs_bake_the_placeholder_engine():
    result = snes.bake(_spec("Top Down", ("topdown_adventure",)))
    assert result.engine == "hello"
    assert len(result.rom) == snes.ROM_SIZES["hello"]
    snes.check_rom(result.rom)
    assert snes.text_data("Top Down") in result.rom
