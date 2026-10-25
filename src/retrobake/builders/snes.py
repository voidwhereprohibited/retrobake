"""SNES builder: game-spec -> playable .sfc ROM (contract "snes-builder", docs/snes-builder.md).

Mirrors the NES builder. The builder only produces *data* (level pack, tile numbers, art,
palettes, a few config bytes chosen from fixed enums) from the spec and drops it next to a fixed
engine template assembled with the PVSnesLib assembler (wla-65816 + wlalink). It never writes
code from user text. Every tool run goes through the security sandbox
(retrobake.security.run_build).

Engines: ``platformer`` (side-view specs, M2) and ``hello`` (title-screen placeholder used for
movement types that have no SNES engine yet).
"""

from __future__ import annotations

import os
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

from . import snes_font, snes_gfx

ENGINE = "platformer"
HELLO = "hello"
MAPPER = "LoROM"
ROM_SIZES = {"platformer": 128 * 1024, "hello": 32 * 1024}
ROM_BYTES = ROM_SIZES[ENGINE]
HEADER = 0x7FC0  # LoROM internal header (file offset, no copier header)
NAME_BYTES = 21
MAP_VRAM = 0x0400  # BG1 tilemap word address in the hello template
CREDIT = "MADE WITH RETROBAKE"
PROMPT = "PRESS START"
TITLE_ROW = 10
PROMPT_ROW = 15
CREDIT_ROW = 24
# platformer title screen (BG3 rows; the engine draws rows < 16 in gold)
P_TITLE_ROW = 7
P_PROMPT_ROW = 17
P_CREDIT_ROW = 22
COMBAT_IDS = {"stomp": 0, "melee": 1, "projectile": 2, "none": 3}
EXTRA_FLAGS = {"hearts": 1, "lives": 2, "collectibles": 4, "score": 8, "timer": 16, "shop": 32}
START_LIVES = 3
START_HEARTS = 3
CONFIG_BYTES = 16
_EXE = ".exe" if sys.platform == "win32" else ""
_PLATFORM = "windows" if sys.platform == "win32" else "linux"
_TOOLS = ("wla-65816", "wlalink")


class SnesBuildError(RuntimeError):
    """Baking failed. ``message`` is plain English and safe to show to the user."""

    def __init__(self, message: str, detail: str = "") -> None:
        super().__init__(f"{message} {detail}".strip())
        self.message = message
        self.detail = detail


@dataclass(frozen=True)
class SnesRom:
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
    return _app_root() / "templates" / "snes"


def find_wladx(wla_dir: str | Path | None = None) -> Path:
    """Folder holding the bundled wla-65816 + wlalink. Raises SnesBuildError if missing."""
    root = _app_root() / "toolchains" / "pvsneslib"
    candidates = [Path(p) for p in (wla_dir, os.environ.get("RETROBAKE_WLA_DIR")) if p]
    candidates += [root / "bin", root / _PLATFORM / "bin"]
    for folder in candidates:
        if all((folder / f"{tool}{_EXE}").is_file() for tool in _TOOLS):
            return folder.resolve()
    raise SnesBuildError(
        "RetroBake's SNES tools are missing. Please reinstall RetroBake.",
        "looked in: " + ", ".join(str(c) for c in candidates),
    )


def _record(row: int, text: str, base: int = MAP_VRAM) -> bytes:
    tiles = snes_font.tiles_for(text)
    if not 1 <= len(tiles) <= 32:
        raise ValueError("a text line must be 1-32 tiles")
    addr = base + row * 32 + (32 - len(tiles)) // 2
    return bytes([len(tiles), addr & 0xFF, addr >> 8]) + tiles


def text_data(title: str, engine: str = HELLO) -> bytes:
    """text.bin: centred title, prompt and credit lines, 0-terminated.

    hello: absolute BG1 VRAM word addresses. platformer: BG3 cell offsets (row * 32 + col).
    """
    if engine == HELLO:
        rows, base = (TITLE_ROW, PROMPT_ROW, CREDIT_ROW), MAP_VRAM
    else:
        rows, base = (P_TITLE_ROW, P_PROMPT_ROW, P_CREDIT_ROW), 0
    lines = (title, PROMPT, CREDIT)
    return b"".join(_record(r, t, base) for r, t in zip(rows, lines, strict=True)) + b"\x00"


def engine_for(spec: dict[str, Any]) -> str:
    """Which SNES engine bakes this spec (side view -> platformer, else the placeholder)."""
    return ENGINE if spec.get("modules", {}).get("movement") == "side_jump" else HELLO


def config_data(spec: dict[str, Any]) -> bytes:
    """config.bin: combat id, extras flags, start lives (BCD), start hearts. Enum-derived only."""
    mods = spec["modules"]
    flags = 0
    for extra in mods.get("extras", []):
        flags |= EXTRA_FLAGS.get(extra, 0)
    lives = START_LIVES if flags & EXTRA_FLAGS["lives"] else 0
    hearts = START_HEARTS if flags & EXTRA_FLAGS["hearts"] else 1
    out = bytes([COMBAT_IDS.get(mods.get("combat"), 0), flags, lives, hearts])
    return out.ljust(CONFIG_BYTES, b"\x00")


def level_data(spec: dict[str, Any]) -> bytes:
    """levels.bin: the RBLV pack from the level-data contract."""
    from retrobake.spec.levels import BUDGETS
    from retrobake.spec.platformer import UnsupportedSpec, generate_levels

    try:
        blob = generate_levels(spec).encode()
    except UnsupportedSpec as exc:
        raise SnesBuildError(exc.message) from exc
    if len(blob) > BUDGETS["snes"] or blob[:4] != b"RBLV" or blob[6] == 0:
        raise SnesBuildError("This game's levels came out too big for the SNES.")
    return blob


def data_files(spec: dict[str, Any], title: str, engine: str) -> dict[str, bytes]:
    """Every data file the engine template .INCBINs, keyed by file name."""
    if engine == HELLO:
        return {"text.bin": text_data(title, HELLO), "font.bin": snes_font.font_bin()}
    hero = spec.get("hero", {}).get("archetype", "explorer")
    mood = spec.get("style", {}).get("palette_mood", "bright")
    return {
        "text.bin": text_data(title, engine),
        "config.bin": config_data(spec),
        "ascii.bin": snes_gfx.ascii_table(),
        "levels.bin": level_data(spec),
        "objtiles.bin": snes_gfx.obj_tiles(hero),
        "objpal.bin": snes_gfx.obj_palettes(hero, mood),
        "hudtiles.bin": snes_gfx.hud_tiles(),
        "hudpal.bin": snes_gfx.hud_palettes(),
        "bg2map.bin": snes_gfx.bg2_maps(),
        "settings.bin": snes_gfx.settings_bin(mood),
    }


def header_name(title: str) -> bytes:
    """21-byte internal ROM name: the title in plain uppercase ASCII, space padded."""
    return title.upper().encode("ascii")[:NAME_BYTES].ljust(NAME_BYTES, b" ")


def checksum(rom: bytes | bytearray) -> int:
    """SNES header checksum (sum of all bytes, with the 4 checksum bytes counted as $1FE)."""
    total = sum(rom) - sum(rom[HEADER + 0x1C : HEADER + 0x20]) + 0x1FE
    return total & 0xFFFF


def _finish(rom: bytes, title: str) -> bytes:
    """Patch the header name and write a fresh checksum + complement."""
    out = bytearray(rom)
    out[HEADER : HEADER + NAME_BYTES] = header_name(title)
    total = checksum(out)
    out[HEADER + 0x1C : HEADER + 0x20] = (total ^ 0xFFFF).to_bytes(2, "little") + total.to_bytes(
        2, "little"
    )
    return bytes(out)


def clean_title(spec: dict[str, Any]) -> str:
    try:
        title = check_title(sanitize("title", spec.get("title", "")))
        snes_font.tiles_for(title)
        header_name(title)
    except InputRejected as exc:
        raise SnesBuildError(exc.message) from exc
    except ValueError as exc:  # includes UnicodeEncodeError
        raise SnesBuildError("The game's name has a character the SNES can't show.") from exc
    return title


def _check_spec(spec: Any) -> None:
    from retrobake.spec import validate

    if not isinstance(spec, dict) or spec.get("system") != "snes":
        raise SnesBuildError("This game isn't set up for the SNES.")
    errors = validate(spec)
    if errors:
        raise SnesBuildError("This game's settings aren't finished yet.", "; ".join(errors))


def bake(
    spec: dict[str, Any],
    *,
    wla_dir: str | Path | None = None,
    limits: BuildLimits | None = None,
) -> SnesRom:
    """Bake ``spec`` into a LoROM .sfc image. Raises SnesBuildError with plain-English text."""
    _check_spec(spec)
    title = clean_title(spec)
    engine = engine_for(spec)
    files = data_files(spec, title, engine)
    tools = find_wladx(wla_dir)
    template = templates_dir() / engine
    if not (template / "main.asm").is_file():
        raise SnesBuildError("RetroBake's SNES game files are missing. Please reinstall RetroBake.")
    size = ROM_SIZES[engine]
    try:
        with BuildWorkspace([templates_dir()], limits) as ws:
            ws.copy_template(template, ".")
            for name, blob in files.items():
                ws.write_file(name, blob)
            steps = [
                [tools / f"wla-65816{_EXE}", "-h", "-o", "main.o", "main.asm"],
                [tools / f"wlalink{_EXE}", "-r", "linkfile", "game.sfc"],
            ]
            isolated = True
            for argv in steps:
                res = run_build(argv, workspace=ws, toolchain_dirs=[tools], limits=limits)
                isolated = isolated and res.network_isolated
                if not res.ok:
                    raise SnesBuildError(
                        "Something went wrong while baking your game.",
                        (res.stderr or res.stdout)[-2000:],
                    )
            rom = ws.read_output("game.sfc", max_bytes=size)
    except SandboxError as exc:
        raise SnesBuildError("Something went wrong while baking your game.", str(exc)) from exc
    check_rom(rom, size)  # the linked template must already be valid before patching
    rom = _finish(rom, title)
    check_rom(rom, size)
    return SnesRom(rom=rom, title=title, engine=engine, mapper=MAPPER, network_isolated=isolated)


def check_rom(rom: bytes, size: int | None = None) -> None:
    """Sanity-check a baked LoROM image (size, map mode, checksum, reset vector).

    ``size`` defaults to any engine's ROM size (32 KB hello or 128 KB platformer).
    """
    problems = []
    sizes = (size,) if size else tuple(ROM_SIZES.values())
    if len(rom) not in sizes:
        problems.append(f"size {len(rom)} not in {sizes}")
    else:
        if rom[HEADER + 0x15] & 0xEF != 0x20:
            problems.append(f"map mode ${rom[HEADER + 0x15]:02X} is not LoROM")
        comp = int.from_bytes(rom[HEADER + 0x1C : HEADER + 0x1E], "little")
        csum = int.from_bytes(rom[HEADER + 0x1E : HEADER + 0x20], "little")
        if csum != checksum(rom) or comp != csum ^ 0xFFFF:
            problems.append("bad header checksum")
        reset = int.from_bytes(rom[0x7FFC:0x7FFE], "little")
        if not 0x8000 <= reset < 0xFFC0:
            problems.append(f"bad reset vector ${reset:04X}")
    if problems:
        raise SnesBuildError("The baked game didn't come out right.", "; ".join(problems))
