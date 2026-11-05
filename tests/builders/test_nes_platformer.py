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


def test_level_data_carries_enemies_and_the_stomp_flag():
    pack = generate_levels(_spec())
    want = [plat._enemies(level) for level in pack.levels]
    assert any(want)
    for stomp in (True, False):
        decoded = plat.decode_level_data(plat.level_data(pack, stomp=stomp))
        assert [d["enemies"] for d in decoded] == want
        assert all(d["stomp"] is stomp for d in decoded)
    for enemies in want:
        assert len(enemies) <= plat.MAX_ENEMIES
        assert all(kind in (plat.WALKER, plat.PATROLLER) for _, _, kind in enemies)


def test_enemy_list_is_capped_and_spread_out():
    level = _flat_level([(lv.WALKER, x, 9) for x in range(4, 100, 4)], width=112)
    enemies = plat._enemies(level)
    assert len(enemies) == plat.MAX_ENEMIES
    assert enemies[0][0] == 4 and enemies[-1][0] > 80
    flyer = _flat_level([(lv.FLYER, 6, 7), (lv.COIN, 7, 9)])
    assert plat._enemies(flyer) == [(6, 7, plat.PATROLLER)]


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
    sprites = chr_rom[4096:]
    for tile in range(16):  # hero, key, flag, heart, walker, patroller
        assert any(sprites[tile * 16 : tile * 16 + 16]), tile


def test_only_side_jump_games_use_this_engine():
    spec = copy.deepcopy(_spec())
    spec["modules"]["movement"] = "top_down"
    with pytest.raises(nes.NesBuildError):
        plat.bake(spec)


def test_check_rom_rejects_garbage():
    with pytest.raises(nes.NesBuildError):
        plat.check_rom(b"NES\x1a" + bytes(100))


# ---------------------------------------------------------------- real builds

QA = 0x7F0  # lives, cam_lo, cam_hi, enemies alive, level, hx_lo, hx_hi, hy
ENEMY_OAM = 28
RUN_SPEED = 2  # pixels per frame (game.s)


def _flat_level(objects, width=32, gaps=()):
    tiles = [bytearray(width) for _ in range(lv.HEIGHT)]
    for x in range(width):
        if x not in gaps:
            tiles[10][x], tiles[11][x] = lv.GROUND, lv.FILL
    objs = [lv.Obj(kind, x, y) for kind, x, y in objects]
    return lv.Level(0, width, tiles, objs, (2, 9), (width - 2, 9), "hills")


def _bake_level(monkeypatch, level, stomp=True):
    data = plat.level_data(lv.LevelPack("nes", 1, [level]), stomp=stomp)
    monkeypatch.setattr(plat, "_levels_for", lambda spec: data)
    return plat.bake(_spec()).rom


def _playing(rom):
    m = Nes(rom)
    m.run(30)
    m.run(3, START)
    m.run(40, 0)
    return m


def _qa(m):
    lives, cam_lo, cam_hi, alive, level, hx_lo, hx_hi, hy = m.ram[QA : QA + 8]
    return {"lives": lives, "cam": cam_lo | cam_hi << 8, "alive": alive, "hx": hx_lo | hx_hi << 8}


def _jump_when_close(m, distance):
    for _ in range(400):
        m.run(1, 0)
        if m.oam[ENEMY_OAM + 3] - m.oam[3] <= distance:
            break
    m.run(3, A)
    m.run(80, 0)


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


@needs_cc65
def test_walker_touch_costs_a_life_and_respawns(monkeypatch):
    m = _playing(_bake_level(monkeypatch, _flat_level([(lv.WALKER, 8, 9)])))
    assert _qa(m) == {"lives": 3, "cam": 0, "alive": 1, "hx": 32}
    assert sum(1 for i in range(160, 172, 4) if m.oam[i] < 0xEF) == 3  # three hearts
    for _ in range(300):
        m.run(1, 0)
        if _qa(m)["lives"] < 3:
            break
    assert _qa(m) == {"lives": 2, "cam": 0, "alive": 1, "hx": 32}  # back at the start


@needs_cc65
@pytest.mark.parametrize("stomp", [True, False])
def test_jumping_on_a_walker(monkeypatch, stomp):
    m = _playing(_bake_level(monkeypatch, _flat_level([(lv.WALKER, 8, 9)]), stomp=stomp))
    _jump_when_close(m, 24)
    if stomp:
        assert _qa(m)["lives"] == 3 and _qa(m)["alive"] == 0
    else:  # avoid-only games: landing on it hurts too
        assert _qa(m)["lives"] == 2 and _qa(m)["alive"] == 1


@needs_cc65
def test_walker_turns_at_ledges_and_patroller_keeps_its_range(monkeypatch):
    level = _flat_level([(lv.WALKER, 9, 9), (lv.FLYER, 11, 7)], gaps=(7, 8, 12))
    m = _playing(_bake_level(monkeypatch, level))
    walker, patroller = set(), set()
    for _ in range(240):
        m.run(1, 0)
        walker.add(m.oam[ENEMY_OAM + 3])
        patroller.add(m.oam[ENEMY_OAM + 16 + 3])
    assert min(walker) == 9 * 16 and max(walker) == 11 * 16  # island is columns 9-11
    assert min(patroller) == 8 * 16 and max(patroller) == 14 * 16  # 11 +/- 3, over the gaps
    assert _qa(m)["lives"] == 3


@needs_cc65
def test_losing_every_life_goes_back_to_the_title(monkeypatch):
    m = _playing(_bake_level(monkeypatch, _flat_level([(lv.WALKER, 5, 9)])))
    for _ in range(600):
        m.run(1, 0)
        if m.ram[0x7FF] == 1:
            break
    assert bytes(m.ram[0x7FC:0x800]) == b"RB\x01\x01"


@needs_cc65
def test_camera_scrolls_smoothly_and_streams_columns(baked):
    m = _playing(baked.rom)
    level = plat.decode_level_data(plat.level_data(generate_levels(_spec())))[0]
    cams = []
    for i in range(150):  # this level's first hazard is further on
        m.run(1, RIGHT | (A if i % 40 == 0 else 0))
        cams.append(_qa(m)["cam"])
    assert _qa(m)["lives"] == 3
    steps = [b - a for a, b in zip(cams, cams[1:], strict=False)]
    assert cams[-1] > 64 and all(0 <= s <= RUN_SPEED for s in steps)  # pixel by pixel
    cam = cams[-1]
    for c in range(cam // 16 + 1, cam // 16 + 16):  # every column in view is in the nametables
        base = (0x2000 if c & 16 == 0 else 0x2400) + 4 * 32 + (c & 15) * 2
        for row in range(lv.HEIGHT):
            tile = level["tiles"][row][c]
            if tile == lv.DOOR:
                continue
            assert m.vram[base + row * 64] == art.META_BASE + tile * 4, (c, row)
