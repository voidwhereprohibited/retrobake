import os

import pytest
from nes_machine import Machine, zp_symbols

from retrobake import spec as gs
from retrobake.builders import nes, nes_gfx
from retrobake.builders import nes_font as font
from retrobake.spec.levels import HEIGHT
from retrobake.spec.platformer import generate_levels

NEED_TOOLS = os.environ.get("RETROBAKE_REQUIRE_CC65") == "1"
ZP = zp_symbols(nes.templates_dir() / "platformer" / "main.s")


def _have_tools() -> bool:
    try:
        nes.find_cc65()
        return True
    except nes.NesBuildError:
        return False


needs_cc65 = pytest.mark.skipif(
    not NEED_TOOLS and not _have_tools(), reason="cc65 not bundled here (CI provides it)"
)


def _spec(title="Hello World", genres=("platformer",), **mods):
    spec, _ = gs.new_spec("nes", list(genres), "a brave fox crosses the hills", title, seed=3)
    spec["modules"].update(mods)
    spec, _ = gs.resolve(spec)
    assert gs.validate(spec) == []
    return spec


VARIANTS = [
    {},
    {"combat": "melee", "extras": ["hearts", "keys_doors", "timer"]},
    {"combat": "projectile", "progression": "dungeons_items", "extras": ["bosses", "shop"]},
    {"combat": "none", "progression": "open_map", "extras": ["collectibles", "lives"]},
]


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


def test_platformer_graphics_bank():
    bank = nes_gfx.chr_bank()
    assert len(bank) == 8192
    for tile in (64, 68, 72, 84, 100, 115, 120, 124, 129):  # sprites, pattern table 1
        assert any(bank[4096 + tile * 16 : 4096 + tile * 16 + 16]), tile
    for t in range(1, 8):  # background metatiles
        assert any(bank[(60 + 4 * t) * 16 : (64 + 4 * t) * 16]), t


def test_text_data_centres_lines_and_terminates():
    data = nes.text_data("HI")
    addr = 0x2000 + nes.TITLE_ROW * 32 + 15
    assert data[:5] == bytes([addr >> 8, addr & 0xFF, 2]) + font.tiles_for("HI")
    assert data[-1] == 0
    assert len(nes.title_data("W" * 24)) < 256


@pytest.mark.parametrize("mods", VARIANTS)
def test_level_blob_matches_generated_levels(mods):
    spec = _spec(**mods)
    pack = generate_levels(spec)
    blob = nes.level_blob(spec, pack)
    assert len(blob) <= nes.LEVELS_MAX
    assert blob[0] == len(pack.levels)
    assert blob[1] == nes.COMBAT_IDS[spec["modules"]["combat"]]
    for i, lv in enumerate(pack.levels):
        e = blob[16 + 16 * i : 32 + 16 * i]
        page, cols = e[0], e[1]
        assert cols == lv.width and (e[5], e[6]) == lv.start and (e[7], e[8]) == lv.goal
        base = (page << 8) - 0x8000
        for x in range(lv.width):
            col = blob[base + x * 16 : base + x * 16 + HEIGHT]
            assert list(col) == [lv.tiles[y][x] for y in range(HEIGHT)]
        objs = (e[10] | e[11] << 8) - 0x8000
        got = [tuple(blob[objs + 3 * k : objs + 3 * k + 3]) for k in range(e[12])]
        assert got == [(o.kind, o.x, o.y) for o in sorted(lv.objects, key=lambda o: o.x)][:40]


def test_engine_choice():
    assert nes.engine_for(_spec()) == "platformer"
    td, _ = gs.new_spec("nes", ["topdown_adventure"], "x", "Hello", seed=1)
    assert nes.engine_for(td) == "hello"


BAD_TITLES = ["", "   ", "Hello`rm -rf`", ".jsr $C000", "\x00boom", "x" * 200]


@pytest.mark.parametrize("bad", BAD_TITLES)
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


def test_missing_toolchain_is_plain_english(tmp_path, monkeypatch):
    monkeypatch.delenv("RETROBAKE_CC65_DIR", raising=False)
    monkeypatch.setattr(nes, "_app_root", lambda: tmp_path)
    with pytest.raises(nes.NesBuildError, match="reinstall"):
        nes.find_cc65(tmp_path)


def test_check_rom_rejects_garbage():
    with pytest.raises(nes.NesBuildError):
        nes.check_rom(b"NES\x1a" + bytes(100))


# ---------------------------------------------------------------- real bakes (CI)


def _zp(m, name, size=1):
    a = ZP[name]
    return m.ram[a] if size == 1 else m.ram[a] | m.ram[a + 1] << 8


def _hero_x(m):
    return _zp(m, "hpx_lo") | _zp(m, "hpx_hi") << 8


def _in_code(m):
    return 0xD000 <= m.cpu.pc <= 0xFFFF


@needs_cc65
def test_topdown_specs_still_bake_the_title_engine():
    td, _ = gs.new_spec("nes", ["topdown_adventure"], "x", "Quest Of Dawn", seed=1)
    result = nes.bake(td)
    assert result.engine == "hello" and len(result.rom) == nes.HELLO_ROM_BYTES
    m = Machine(result.rom)
    m.run_frames(30)
    assert m.ram_sig() == b"RB\x01\x01"
    m.hold(Machine.START, 10)
    m.run_frames(5)
    assert m.ram_sig() == b"RB\x01\x02"


@needs_cc65
def test_platformer_title_start_and_play():
    result = nes.bake(_spec("Fox & Hills: 2!"))
    assert result.engine == "platformer" and result.mapper == "NROM-256"
    assert len(result.rom) == nes.ROM_BYTES and result.rom[4] == 2
    m = Machine(result.rom)
    m.run_frames(40)
    assert m.ram_sig() == b"RB\x01\x01"  # title screen
    assert font.tiles_for("Fox & Hills: 2!") in m.nametable_text(10)
    assert font.tiles_for("PRESS START") in m.nametable_text(16)

    m.hold(Machine.START, 5)
    m.run_frames(10)
    assert m.ram_sig() == b"RB\x01\x02"  # gameplay from here on
    assert font.tiles_for("STAGE 1") in m.nametable_text(12)

    m.run_frames(140)  # stage card times out, level 1 starts
    assert m.ppumask == 0x1E and _zp(m, "busy") == 0
    assert any(s[1] in (64, 68) for s in m.sprites()), "hero sprite on screen"
    assert any(m.vram[0x2000 + r * 32] >= 64 for r in range(24)), "level tiles drawn"
    assert _zp(m, "on_ground") == 1

    x0 = _hero_x(m)
    m.hold(Machine.RIGHT, 60)
    assert _hero_x(m) > x0 + 40, "hero runs right"
    assert _in_code(m)

    m.run_frames(30)
    if _zp(m, "event") == 0 and _zp(m, "on_ground"):
        y0 = _zp(m, "hpy")
        m.hold(Machine.A, 12)
        assert _zp(m, "hpy") < y0 - 30, "hero jumps at least 2 tiles"
        m.run_frames(60)


@needs_cc65
@pytest.mark.parametrize("mods", VARIANTS)
def test_every_variant_bakes_and_survives_a_bot(mods):
    spec = _spec("Bot Run", **mods)
    a = nes.bake(spec).rom
    assert a == nes.bake(spec).rom  # deterministic
    m = Machine(a)
    m.run_frames(20)
    m.hold(Machine.START, 4)
    m.run_frames(140)
    for i in range(8):  # run right, jump, attack: the game must keep running sanely
        m.hold(Machine.RIGHT | (Machine.A if i % 2 else 0) | Machine.B, 20)
        assert _in_code(m), f"CPU left the engine code at ${m.cpu.pc:04X}"
        assert m.ram_sig()[:3] == b"RB\x01" and m.ram_sig()[3] == 2
        assert m.cpu.sp > 0xC0, "stack is not leaking"
