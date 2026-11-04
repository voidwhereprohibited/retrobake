import copy
import hashlib
import os

import pytest
from cpu6502 import Nes

from retrobake import spec as gs
from retrobake.builders import nes
from retrobake.builders import nes_platformer as plat
from retrobake.builders import nes_platformer_art as art
from retrobake.spec import levels as lv
from retrobake.spec.platformer import generate_levels

NEED_TOOLS = os.environ.get("RETROBAKE_REQUIRE_CC65") == "1"
START, RIGHT, A = 0x10, 0x01, 0x80


def _have_tools() -> bool:
    try:
        nes.find_cc65()
        return True
    except nes.NesBuildError:
        return False


needs_cc65 = pytest.mark.skipif(
    not NEED_TOOLS and not _have_tools(), reason="cc65 not bundled here (CI provides it)"
)


def _spec(title="Fox Hills", seed=3, template=None):
    spec, _ = gs.new_spec(
        "nes", "platformer", "a brave fox crosses the hills", title, seed=seed, template=template
    )
    return spec


@pytest.fixture(scope="module")
def baked():
    if not NEED_TOOLS and not _have_tools():
        pytest.skip("cc65 not bundled here (CI provides it)")
    return plat.bake(_spec())


# ---------------------------------------------------------------- pure data


def test_vendored_files_match_their_recorded_hashes():
    root = plat.third_party_dir()
    lines = (root / "SHA256SUMS").read_text().split("\n")
    entries = [line.split(maxsplit=1) for line in lines if line.strip()]
    assert len(entries) >= 13
    for digest, name in entries:
        assert hashlib.sha256((root / name.strip()).read_bytes()).hexdigest() == digest, name
    assert (root / "THIRD_PARTY_NOTICES").is_file()


def test_note_tables_are_identical_to_famistudio_upstream():
    tables = plat.checked_note_tables()
    assert all(len(t) == plat.NOTE_COUNT for t in tables.values())


@pytest.mark.parametrize("seed", [1, 3, 7])
def test_level_data_round_trips(seed):
    pack = generate_levels(_spec(seed=seed))
    decoded = plat.decode_level_data(plat.level_data(pack))
    assert len(decoded) == len(pack.levels)
    for level, got in zip(pack.levels, decoded, strict=True):
        assert got["width"] == level.width
        assert got["start"] == tuple(level.start)
        assert got["goal"] == tuple(level.goal)
        assert got["tiles"] == [bytearray(row) for row in level.tiles]
        keys = [(o.x, o.y) for o in level.objects if o.kind == lv.KEY]
        assert got["key"] == (keys[0] if keys else None)


def test_level_data_rejects_what_the_engine_cannot_hold():
    pack = generate_levels(_spec())
    level = pack.levels[0]
    level.width = 20
    with pytest.raises(ValueError):
        plat.level_data(pack)


def test_art_fits_the_pattern_tables():
    chr_rom = art.chr_rom()
    assert len(chr_rom) == 8192
    meta = chr_rom[art.META_BASE * 16 : (art.META_BASE + 32) * 16]
    assert any(meta[64:])  # ground is not blank
    assert any(chr_rom[4096 : 4096 + 7 * 16])  # hero, key and flag sprites


def test_only_side_jump_games_use_this_engine():
    spec = copy.deepcopy(_spec())
    spec["modules"]["movement"] = "top_down"
    with pytest.raises(nes.NesBuildError):
        plat.bake(spec)


def test_check_rom_rejects_garbage():
    with pytest.raises(nes.NesBuildError):
        plat.check_rom(b"NES\x1a" + bytes(100))


# ---------------------------------------------------------------- real builds


@needs_cc65
def test_rom_builds_with_a_valid_ines_header(baked):
    rom = baked.rom
    assert len(rom) == plat.ROM_BYTES == 40976
    assert rom[:8] == b"NES\x1a\x02\x01\x01\x00" and not any(rom[8:16])
    assert baked.engine == "platformer" and baked.mapper == "NROM-256"
    assert rom[16 + 0x8000 :] == art.chr_rom()
    assert plat.level_data(generate_levels(_spec())) in rom


@needs_cc65
def test_bake_is_deterministic(baked):
    assert plat.bake(_spec()).rom == baked.rom


def _hero_x(m: Nes) -> int:
    return m.oam[3]


def _hero_y(m: Nes) -> int:
    return m.oam[0]


@needs_cc65
def test_rom_boots_to_title_then_plays(baked):
    m = Nes(baked.rom)
    m.run(30)
    assert bytes(m.ram[0x7FC:0x800]) == b"RB\x01\x01"  # title screen
    title = bytes(m.vram[0x2000 + nes.TITLE_ROW * 32 : 0x2000 + nes.TITLE_ROW * 32 + 32])
    assert any(title)
    music = len(m.apu_writes)
    assert music > 0

    m.run(3, START)
    m.run(40, 0)
    assert bytes(m.ram[0x7FC:0x800]) == b"RB\x01\x02"  # gameplay
    assert m.ppu_ctrl & 0x08  # sprites come from $1000
    assert m.oam[1] == 0 and _hero_y(m) < 0xEF  # hero drawn
    assert any(m.vram[0x2080:0x2400])  # level drawn
    assert len(m.apu_writes) > music  # music keeps playing

    x0, y0 = _hero_x(m), _hero_y(m)
    m.run(20, RIGHT)
    assert _hero_x(m) > x0  # walks right
    m.run(30, 0)
    ground = _hero_y(m)
    assert ground >= y0
    m.run(10, A)
    assert _hero_y(m) < ground - 16  # jumps
    m.run(60, 0)
    assert _hero_y(m) == ground  # lands again
    assert bytes(m.ram[0x7FC:0x800]) == b"RB\x01\x02"
