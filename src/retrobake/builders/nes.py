"""NES builder: game-spec -> playable .nes ROM (contract "nes-builder", docs/nes-builder.md).

The builder only produces *data* (tile numbers, level maps, CHR graphics) from the spec and
drops it next to a fixed engine template. It never writes code from user text. Every tool
run goes through the security sandbox (retrobake.security.run_build).

Engines:
  platformer - side-view specs (movement "side_jump"), NROM-256, levels from game-design's
               generator (retrobake.spec.platformer.generate_levels)
  hello      - title screen only, used for top-down specs until the M3 engine lands
"""

from __future__ import annotations

import os
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from retrobake.security import (
    BuildLimits,
    BuildWorkspace,
    InputRejected,
    SandboxError,
    check_title,
    run_build,
    sanitize,
)

from . import nes_font, nes_gfx

HEADER_BYTES = 16
CHR_BYTES = 8 * 1024
ENGINES = {
    # engine: (linker config, PRG banks of 16 KB, mapper name)
    "platformer": ("nrom256.cfg", 2, "NROM-256"),
    "hello": ("nrom.cfg", 1, "NROM-128"),
}
ENGINE = "platformer"
MAPPER = "NROM-256"
ROM_BYTES = HEADER_BYTES + 2 * 16384 + CHR_BYTES  # platformer ROM size
HELLO_ROM_BYTES = HEADER_BYTES + 16384 + CHR_BYTES
CREDIT = "MADE WITH RETROBAKE"
TITLE_ROW = 12
CREDIT_ROW = 22
LEVELS_ADDR = 0x8000
LEVELS_MAX = 0x5000  # $8000-$CFFF
MAX_OBJECTS = 40
COMBAT_IDS = {"stomp": 0, "melee": 1, "projectile": 2, "none": 3}
FLAG_BITS = {"hearts": 1, "lives": 2, "collectibles": 4, "timer": 8}
STRINGS = {
    "str_stage": "STAGE ",
    "str_lives": "LIVES ",
    "str_gameover": "GAME OVER",
    "str_end": "THE END",
    "str_thanks": "THANKS FOR PLAYING",
}
_EXE = ".exe" if sys.platform == "win32" else ""
_PLATFORM = "windows" if sys.platform == "win32" else "linux"


class NesBuildError(RuntimeError):
    """Baking failed. ``message`` is plain English and safe to show to the user."""

    def __init__(self, message: str, detail: str = "") -> None:
        super().__init__(f"{message} {detail}".strip())
        self.message = message
        self.detail = detail


@dataclass(frozen=True)
class NesRom:
    rom: bytes
    title: str
    engine: str
    mapper: str
    network_isolated: bool


def _app_root() -> Path:
    frozen = getattr(sys, "_MEIPASS", None)
    if frozen:
        return Path(frozen)
    return Path(__file__).resolve().parents[3]  # src/retrobake/builders -> repo root


def templates_dir() -> Path:
    return _app_root() / "templates" / "nes"


def find_cc65(cc65_dir: str | Path | None = None) -> Path:
    """Folder holding the bundled ca65 + ld65. Raises NesBuildError if they're missing."""
    root = _app_root() / "toolchains" / "cc65"
    candidates = [Path(p) for p in (cc65_dir, os.environ.get("RETROBAKE_CC65_DIR")) if p]
    candidates += [root / "bin", root / _PLATFORM / "bin"]
    for folder in candidates:
        if all((folder / f"{tool}{_EXE}").is_file() for tool in ("ca65", "ld65")):
            return folder.resolve()
    raise NesBuildError(
        "RetroBake's NES tools are missing. Please reinstall RetroBake.",
        "looked in: " + ", ".join(str(c) for c in candidates),
    )


# ---------------------------------------------------------------- data files


def _record(row: int, text: str) -> bytes:
    tiles = nes_font.tiles_for(text)
    if not 1 <= len(tiles) <= 32:
        raise ValueError("a text line must be 1-32 tiles")
    addr = 0x2000 + row * 32 + (32 - len(tiles)) // 2
    return bytes([addr >> 8, addr & 0xFF, len(tiles)]) + tiles


def text_data(title: str) -> bytes:
    """hello engine text.bin: centred title + credit line, 0-terminated."""
    return _record(TITLE_ROW, title) + _record(CREDIT_ROW, CREDIT) + b"\x00"


def title_data(title: str) -> bytes:
    """platformer title.bin: title, PRESS START, credit."""
    return _record(10, title) + _record(16, "PRESS START") + _record(25, CREDIT) + b"\x00"


def string_data(text: str) -> bytes:
    tiles = nes_font.tiles_for(text)
    return bytes([len(tiles)]) + tiles


def engine_for(spec: dict[str, Any]) -> str:
    return "platformer" if spec["modules"]["movement"] == "side_jump" else "hello"


def level_blob(spec: dict[str, Any], pack: Any) -> bytes:
    """levels.bin for the platformer engine (layout documented in its main.s).

    Converts game-design's LevelPack into the engine's ROM layout: config, a level table,
    object lists and uncompressed, page-aligned 16-byte columns the 6502 can index directly.
    """
    from retrobake.spec import catalog
    from retrobake.spec.levels import HEIGHT

    settings = list(catalog()["settings"])
    mods = spec["modules"]
    extras = set(mods["extras"])
    levels = pack.levels
    if not 1 <= len(levels) <= 8:
        raise ValueError("the NES engine holds 1-8 stages")
    flags = sum(bit for name, bit in FLAG_BITS.items() if name in extras)
    head = bytearray(16)
    head[0:5] = bytes(
        [
            len(levels),
            COMBAT_IDS[mods["combat"]],
            flags,
            3 if "hearts" in extras else 1,
            3,  # lives (only counted down when the "lives" extra is on)
        ]
    )
    table_at = 16
    objs_at = table_at + 16 * len(levels)
    obj_bytes = bytearray()
    obj_addrs = []
    for lv in levels:
        objs = sorted(lv.objects, key=lambda o: o.x)[:MAX_OBJECTS]
        obj_addrs.append((LEVELS_ADDR + objs_at + len(obj_bytes), len(objs)))
        for o in objs:
            if not (1 <= o.kind <= 9 and 0 <= o.x < lv.width and 0 <= o.y < HEIGHT):
                raise ValueError("object out of range")
            obj_bytes += bytes([o.kind, o.x, o.y])
    maps_at = objs_at + len(obj_bytes)
    maps_at = (maps_at + 255) & ~255
    maps = bytearray()
    table = bytearray()
    for lv, (obj_addr, n_obj) in zip(levels, obj_addrs, strict=True):
        if lv.width % 16 or not 16 <= lv.width <= 128:
            raise ValueError("NES levels are 1-8 screens wide")
        page = (LEVELS_ADDR + maps_at + len(maps)) >> 8
        for x in range(lv.width):
            column = bytes(lv.tiles[y][x] for y in range(HEIGHT))
            if max(column) > 7:
                raise ValueError("unknown tile")
            maps += column + bytes(16 - HEIGHT)
        sx, sy = lv.start
        gx, gy = lv.goal
        flags_l = (1 if lv.boss else 0) | (2 if lv.key_door else 0)
        t = lv.time_limit if "timer" in extras else 0
        table += struct.pack(
            "<BBBHBBBBBHB3x",
            page,
            lv.width,
            flags_l,
            t,
            sx,
            sy,
            gx,
            gy,
            settings.index(lv.setting),
            obj_addr,
            n_obj,
        )
    blob = bytes(head + table + obj_bytes)
    blob += bytes(maps_at - len(blob)) + bytes(maps)
    if len(blob) > LEVELS_MAX:
        raise ValueError("level data is too big for the NES")
    return blob


def clean_title(spec: dict[str, Any]) -> str:
    try:
        title = check_title(sanitize("title", spec.get("title", "")))
        nes_font.tiles_for(title)
    except InputRejected as exc:
        raise NesBuildError(exc.message) from exc
    except ValueError as exc:
        raise NesBuildError("The game's name has a character the NES can't show.") from exc
    return title


def _check_spec(spec: Any) -> None:
    from retrobake.spec import validate

    if not isinstance(spec, dict) or spec.get("system") != "nes":
        raise NesBuildError("This game isn't set up for the NES.")
    errors = validate(spec)
    if errors:
        raise NesBuildError("This game's settings aren't finished yet.", "; ".join(errors))


def engine_files(spec: dict[str, Any], title: str) -> tuple[str, dict[str, bytes]]:
    """(engine, {file name: data}) for the template. Data only, never source code."""
    engine = engine_for(spec)
    if engine == "hello":
        return engine, {"text.bin": text_data(title), "font.chr": nes_font.chr_bank()}
    from retrobake.spec.platformer import UnsupportedSpec, generate_levels

    try:
        pack = generate_levels(spec)
        levels = level_blob(spec, pack)
    except UnsupportedSpec as exc:
        raise NesBuildError(exc.message) from exc
    except ValueError as exc:
        raise NesBuildError("This game's levels don't fit on the NES.", str(exc)) from exc
    files = {"levels.bin": levels, "title.bin": title_data(title), "gfx.chr": nes_gfx.chr_bank()}
    files.update({f"{name}.bin": string_data(text) for name, text in STRINGS.items()})
    return engine, files


def bake(
    spec: dict[str, Any],
    *,
    cc65_dir: str | Path | None = None,
    limits: BuildLimits | None = None,
) -> NesRom:
    """Bake ``spec`` into an iNES ROM. Raises NesBuildError with plain-English text."""
    _check_spec(spec)
    title = clean_title(spec)
    tools = find_cc65(cc65_dir)
    engine, files = engine_files(spec, title)
    cfg, banks, mapper = ENGINES[engine]
    template = templates_dir() / engine
    if not (template / "main.s").is_file():
        raise NesBuildError("RetroBake's NES game files are missing. Please reinstall RetroBake.")
    size = HEADER_BYTES + banks * 16384 + CHR_BYTES
    try:
        with BuildWorkspace([templates_dir()], limits) as ws:
            ws.copy_template(template, ".")
            for name, data in files.items():
                ws.write_file(name, data)
            steps = [
                [tools / f"ca65{_EXE}", "--cpu", "6502", "-o", "main.o", "main.s"],
                [tools / f"ld65{_EXE}", "-C", cfg, "-o", "game.nes", "main.o"],
            ]
            isolated = True
            for argv in steps:
                res = run_build(argv, workspace=ws, toolchain_dirs=[tools], limits=limits)
                isolated = isolated and res.network_isolated
                if not res.ok:
                    raise NesBuildError(
                        "Something went wrong while baking your game.",
                        (res.stderr or res.stdout)[-2000:],
                    )
            rom = ws.read_output("game.nes", max_bytes=size)
    except SandboxError as exc:
        raise NesBuildError("Something went wrong while baking your game.", str(exc)) from exc
    check_rom(rom)
    return NesRom(rom=rom, title=title, engine=engine, mapper=mapper, network_isolated=isolated)


def check_rom(rom: bytes) -> None:
    """Sanity-check a baked NROM image (header, size, reset vector)."""
    problems = []
    banks = rom[4] if len(rom) > 5 else 0
    if banks not in (1, 2) or len(rom) != HEADER_BYTES + banks * 16384 + CHR_BYTES:
        problems.append(f"size {len(rom)} does not match {banks} PRG banks")
    if rom[:4] != b"NES\x1a" or rom[5:6] != b"\x01" or rom[6] >> 4 or rom[7] & 0xF0:
        problems.append("bad iNES header")
    vec = HEADER_BYTES + banks * 16384 - 4  # reset vector at $FFFC
    reset = rom[vec] | rom[vec + 1] << 8 if banks and len(rom) >= vec + 2 else 0
    low = 0x10000 - banks * 16384
    if not low <= reset < 0xFFFA:
        problems.append(f"bad reset vector ${reset:04X}")
    if problems:
        raise NesBuildError("The baked game didn't come out right.", "; ".join(problems))
