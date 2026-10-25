"""SNES builder: game-spec -> playable .sfc ROM (contract "snes-builder", docs/snes-builder.md).

Mirrors the NES builder. The builder only produces *data* (tile numbers, 2bpp font tiles)
from the spec and drops it next to a fixed engine template assembled with the PVSnesLib
assembler (wla-65816 + wlalink). It never writes code from user text. Every tool run goes
through the security sandbox (retrobake.security.run_build).
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

from . import snes_font

ENGINE = "hello"
MAPPER = "LoROM"
ROM_BYTES = 32 * 1024
HEADER = 0x7FC0  # LoROM internal header (file offset, no copier header)
NAME_BYTES = 21
MAP_VRAM = 0x0400  # BG1 tilemap word address in the template
CREDIT = "MADE WITH RETROBAKE"
PROMPT = "PRESS START"
TITLE_ROW = 10
PROMPT_ROW = 15
CREDIT_ROW = 24
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


def _record(row: int, text: str) -> bytes:
    tiles = snes_font.tiles_for(text)
    if not 1 <= len(tiles) <= 32:
        raise ValueError("a text line must be 1-32 tiles")
    addr = MAP_VRAM + row * 32 + (32 - len(tiles)) // 2
    return bytes([len(tiles), addr & 0xFF, addr >> 8]) + tiles


def text_data(title: str) -> bytes:
    """text.bin for the template: centred title, prompt and credit lines, 0-terminated."""
    return (
        _record(TITLE_ROW, title)
        + _record(PROMPT_ROW, PROMPT)
        + _record(CREDIT_ROW, CREDIT)
        + b"\x00"
    )


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
    tools = find_wladx(wla_dir)
    template = templates_dir() / ENGINE
    if not (template / "main.asm").is_file():
        raise SnesBuildError(
            "RetroBake's SNES game files are missing. Please reinstall RetroBake."
        )
    try:
        with BuildWorkspace([templates_dir()], limits) as ws:
            ws.copy_template(template, ".")
            ws.write_file("text.bin", text_data(title))
            ws.write_file("font.bin", snes_font.font_bin())
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
            rom = ws.read_output("game.sfc", max_bytes=ROM_BYTES)
    except SandboxError as exc:
        raise SnesBuildError("Something went wrong while baking your game.", str(exc)) from exc
    check_rom(rom)  # the linked template must already be valid before patching
    rom = _finish(rom, title)
    check_rom(rom)
    return SnesRom(rom=rom, title=title, engine=ENGINE, mapper=MAPPER, network_isolated=isolated)


def check_rom(rom: bytes) -> None:
    """Sanity-check a baked 32 KB LoROM image (size, map mode, checksum, reset vector)."""
    problems = []
    if len(rom) != ROM_BYTES:
        problems.append(f"size {len(rom)} != {ROM_BYTES}")
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
