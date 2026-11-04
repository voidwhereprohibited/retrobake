"""NES platformer builder: side-jump game-spec -> playable NROM-256 .nes ROM.

The engine (templates/nes/platformer) is fixed RetroBake assembly linked with the vendored
neslib/nesdoug library and FamiStudio sound engine (third_party/, see THIRD_PARTY_NOTICES).
This module only generates *data* for it: the level table from ``spec.platformer``, the
title-screen text records, placeholder CHR graphics and FamiStudio's note tables. Every tool
run goes through the security sandbox, like the "hello" builder in ``nes.py``.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from retrobake.security import BuildLimits, BuildWorkspace, SandboxError, run_build
from retrobake.spec import levels as lv

from . import nes, nes_platformer_art

ENGINE = "platformer"
MAPPER = "NROM-256"
PRG_BYTES = 32 * 1024
ROM_BYTES = nes.HEADER_BYTES + PRG_BYTES + nes.CHR_BYTES
MAX_LEVELS = 16
MAX_COLUMNS = 42  # unique columns per level; column offsets must fit in one byte (x6)
MAX_LEVEL_BYTES = 8192
LEVEL_HEADER = 8
PRESS_START = "PRESS START"
PRESS_ROW = 16

# FamiStudio's NTSC note tables (NoteTables/famistudio_note_table_{lsb,msb}.bin upstream).
# We compute them instead of shipping binaries and check them against upstream's hashes.
NOTE_TABLE_SHA256 = {
    "famistudio_note_table_lsb.bin": (
        "b917b0ebbe96945bbf6237bf2c59c9d1cf35f64e4e8183bece0f45d32486ee41"
    ),
    "famistudio_note_table_msb.bin": (
        "b52e4924c607af3369e3de8da5ea9001dc013e67b515d3b3b09dab17601169fb"
    ),
}
CPU_HZ_NTSC = 1789773
NOTE_COUNT = 97  # entry 0 = silence, then C0..C8; entry 46 is A4 (440 Hz)

_ASM = ("startup.s", "game.s", "music.s", "famistudio_glue.s")


def third_party_dir() -> Path:
    return nes._app_root() / "third_party"


def note_tables() -> dict[str, bytes]:
    lsb, msb = bytearray(NOTE_COUNT), bytearray(NOTE_COUNT)
    for i in range(1, NOTE_COUNT):
        freq = 440 * 2 ** ((i - 46) / 12)
        period = round(CPU_HZ_NTSC / (16 * freq) - 1)
        lsb[i], msb[i] = period & 0xFF, period >> 8
    return {
        "famistudio_note_table_lsb.bin": bytes(lsb),
        "famistudio_note_table_msb.bin": bytes(msb),
    }


def checked_note_tables() -> dict[str, bytes]:
    tables = note_tables()
    for name, data in tables.items():
        if hashlib.sha256(data).hexdigest() != NOTE_TABLE_SHA256[name]:
            raise nes.NesBuildError(
                "RetroBake's NES music tables don't match. Please reinstall RetroBake.", name
            )
    return tables


# ---------------------------------------------------------------- level data


def _pack_column(col: bytes) -> bytes:
    return bytes(col[r] | col[r + 1] << 4 for r in range(0, lv.HEIGHT, 2))


def _unpack_column(data: bytes) -> bytes:
    out = bytearray()
    for b in data:
        out += bytes((b & 0x0F, b >> 4))
    return bytes(out)


def _level_record(level: lv.Level) -> bytes:
    if not 1 <= level.width <= 128 or level.width % lv.SCREEN_WIDTH:
        raise ValueError(f"level {level.index}: width {level.width} doesn't fit the NES engine")
    columns: dict[bytes, int] = {}
    col_map = bytearray()
    for x in range(level.width):
        col = bytes(level.tiles[y][x] for y in range(lv.HEIGHT))
        if max(col) > 0x0F:
            raise ValueError(f"level {level.index}: tile id out of range")
        col_map.append(columns.setdefault(col, len(columns)))
    if len(columns) > MAX_COLUMNS:
        raise ValueError(
            f"level {level.index}: {len(columns)} different columns (max {MAX_COLUMNS})"
        )
    key = next(((o.x, o.y) for o in level.objects if o.kind == lv.KEY), (0xFF, 0xFF))
    head = bytes([level.width, *level.start, *level.goal, *key, len(columns)])
    return head + bytes(col_map) + b"".join(_pack_column(c) for c in columns)


def level_data(pack: lv.LevelPack) -> bytes:
    """levels.bin for the engine.

    Layout: ``count``, then ``count`` little-endian offsets (from the start of the data), then
    one record per level: ``width, start_x, start_y, goal_x, goal_y, key_x, key_y`` (key
    $FF/$FF when there is none), ``n_columns``, a ``width``-byte column map, then ``n_columns``
    unique columns of 6 bytes (12 rows, two 4-bit tiles per byte, even row in the low nibble).
    Unlike the RBLV pack, the 6502 can read any tile straight from ROM in a few steps.
    """
    levels = pack.levels
    if not 1 <= len(levels) <= MAX_LEVELS:
        raise ValueError(f"{len(levels)} levels (the NES engine takes 1-{MAX_LEVELS})")
    records = [_level_record(level) for level in levels]
    offsets, pos = [], 1 + 2 * len(records)
    for rec in records:
        offsets.append(pos)
        pos += len(rec)
    if pos > MAX_LEVEL_BYTES:
        raise ValueError(f"level data is {pos} bytes (max {MAX_LEVEL_BYTES})")
    head = bytes([len(records)]) + b"".join(o.to_bytes(2, "little") for o in offsets)
    return head + b"".join(records)


def decode_level_data(data: bytes) -> list[dict[str, Any]]:
    """Inverse of ``level_data`` (for tests and tools)."""
    out = []
    count = data[0]
    for i in range(count):
        pos = int.from_bytes(data[1 + 2 * i : 3 + 2 * i], "little")
        width, sx, sy, gx, gy, kx, ky, ncols = data[pos : pos + LEVEL_HEADER]
        col_map = data[pos + LEVEL_HEADER : pos + LEVEL_HEADER + width]
        base = pos + LEVEL_HEADER + width
        cols = [_unpack_column(data[base + 6 * c : base + 6 * c + 6]) for c in range(ncols)]
        tiles = [bytearray(cols[col_map[x]][y] for x in range(width)) for y in range(lv.HEIGHT)]
        key = None if (kx, ky) == (0xFF, 0xFF) else (kx, ky)
        out.append(
            {"width": width, "start": (sx, sy), "goal": (gx, gy), "key": key, "tiles": tiles}
        )
    return out


def title_text(title: str) -> bytes:
    return (
        nes._record(nes.TITLE_ROW, title)
        + nes._record(PRESS_ROW, PRESS_START)
        + nes._record(nes.CREDIT_ROW, nes.CREDIT)
        + b"\x00"
    )


# ---------------------------------------------------------------- bake


def _levels_for(spec: dict[str, Any]) -> bytes:
    from retrobake.spec.platformer import generate_levels

    if spec.get("modules", {}).get("movement") != "side_jump":
        raise nes.NesBuildError("The NES platformer engine only makes side-view jumping games.")
    try:
        return level_data(generate_levels(spec))
    except ValueError as exc:
        raise nes.NesBuildError("This game's levels are too big for the NES.", str(exc)) from exc


def bake(
    spec: dict[str, Any],
    *,
    cc65_dir: str | Path | None = None,
    limits: BuildLimits | None = None,
) -> nes.NesRom:
    """Bake a side-jump ``spec`` into a playable NROM-256 ROM. Raises nes.NesBuildError."""
    nes._check_spec(spec)
    title = nes.clean_title(spec)
    levels = _levels_for(spec)
    tables = checked_note_tables()
    tools = nes.find_cc65(cc65_dir)
    template = nes.templates_dir() / ENGINE
    lib = third_party_dir()
    if (
        not (template / "game.s").is_file()
        or not (lib / "famistudio" / "famistudio_ca65.s").is_file()
    ):
        raise nes.NesBuildError(
            "RetroBake's NES game files are missing. Please reinstall RetroBake."
        )
    ca65, ld65 = tools / f"ca65{nes._EXE}", tools / f"ld65{nes._EXE}"
    steps = [
        [ca65, "--cpu", "6502", "-I", "lib", "-I", "famistudio", "-o", name[:-2] + ".o", name]
        for name in _ASM
    ]
    steps.append([ld65, "-C", "nrom256.cfg", "-o", "game.nes", *(n[:-2] + ".o" for n in _ASM)])
    try:
        with BuildWorkspace([nes.templates_dir(), lib], limits) as ws:
            ws.copy_template(template, ".")
            ws.copy_template(lib / "nesdoug" / "LIB", "lib")
            ws.copy_template(lib / "famistudio", "famistudio")
            for name, data in tables.items():
                ws.write_file(f"NoteTables/{name}", data)
            ws.write_file("levels.bin", levels)
            ws.write_file("text.bin", title_text(title))
            ws.write_file("game.chr", nes_platformer_art.chr_rom())
            isolated = True
            for argv in steps:
                res = run_build(argv, workspace=ws, toolchain_dirs=[tools], limits=limits)
                isolated = isolated and res.network_isolated
                if not res.ok:
                    raise nes.NesBuildError(
                        "Something went wrong while baking your game.",
                        (res.stderr or res.stdout)[-2000:],
                    )
            rom = ws.read_output("game.nes", max_bytes=ROM_BYTES)
    except SandboxError as exc:
        raise nes.NesBuildError("Something went wrong while baking your game.", str(exc)) from exc
    check_rom(rom)
    return nes.NesRom(rom=rom, title=title, engine=ENGINE, mapper=MAPPER, network_isolated=isolated)


def check_rom(rom: bytes) -> None:
    """Sanity-check a baked NROM-256 image (iNES header, size, vectors)."""
    problems = []
    if len(rom) != ROM_BYTES:
        problems.append(f"size {len(rom)} != {ROM_BYTES}")
    if rom[:4] != b"NES\x1a" or rom[4:6] != b"\x02\x01" or rom[6] != 0x01 or rom[7] != 0:
        problems.append("bad iNES header")
    if any(rom[8:16]):
        problems.append("iNES header padding isn't zero")
    vec = nes.HEADER_BYTES + PRG_BYTES - 6
    for name, at in (("nmi", vec), ("reset", vec + 2), ("irq", vec + 4)):
        addr = rom[at] | rom[at + 1] << 8 if len(rom) >= at + 2 else 0
        if not 0x8000 <= addr < 0xFFFA:
            problems.append(f"bad {name} vector ${addr:04X}")
    if problems:
        raise nes.NesBuildError("The baked game didn't come out right.", "; ".join(problems))
