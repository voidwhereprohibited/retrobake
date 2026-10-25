"""NES builder: game-spec -> playable .nes ROM (contract "nes-builder", docs/nes-builder.md).

The builder only produces *data* (tile numbers, CHR graphics) from the spec and drops it
next to a fixed engine template. It never writes code from user text. Every tool run goes
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

from . import nes_font

ENGINE = "hello"
MAPPER = "NROM-128"
HEADER_BYTES = 16
PRG_BYTES = 16 * 1024
CHR_BYTES = 8 * 1024
ROM_BYTES = HEADER_BYTES + PRG_BYTES + CHR_BYTES
CREDIT = "MADE WITH RETROBAKE"
TITLE_ROW = 12
CREDIT_ROW = 22
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


def _record(row: int, text: str) -> bytes:
    tiles = nes_font.tiles_for(text)
    if not 1 <= len(tiles) <= 32:
        raise ValueError("a text line must be 1-32 tiles")
    addr = 0x2000 + row * 32 + (32 - len(tiles)) // 2
    return bytes([addr >> 8, addr & 0xFF, len(tiles)]) + tiles


def text_data(title: str) -> bytes:
    """text.bin for the template: centred title + credit line, 0-terminated."""
    return _record(TITLE_ROW, title) + _record(CREDIT_ROW, CREDIT) + b"\x00"


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
    template = templates_dir() / ENGINE
    if not (template / "main.s").is_file():
        raise NesBuildError("RetroBake's NES game files are missing. Please reinstall RetroBake.")
    try:
        with BuildWorkspace([templates_dir()], limits) as ws:
            ws.copy_template(template, ".")
            ws.write_file("text.bin", text_data(title))
            ws.write_file("font.chr", nes_font.chr_bank())
            steps = [
                [tools / f"ca65{_EXE}", "--cpu", "6502", "-o", "main.o", "main.s"],
                [tools / f"ld65{_EXE}", "-C", "nrom.cfg", "-o", "game.nes", "main.o"],
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
            rom = ws.read_output("game.nes", max_bytes=ROM_BYTES)
    except SandboxError as exc:
        raise NesBuildError("Something went wrong while baking your game.", str(exc)) from exc
    check_rom(rom)
    return NesRom(rom=rom, title=title, engine=ENGINE, mapper=MAPPER, network_isolated=isolated)


def check_rom(rom: bytes) -> None:
    """Sanity-check a baked NROM-128 image (header, size, reset vector)."""
    problems = []
    if len(rom) != ROM_BYTES:
        problems.append(f"size {len(rom)} != {ROM_BYTES}")
    if rom[:4] != b"NES\x1a" or rom[4:6] != b"\x01\x01" or rom[6] >> 4 or rom[7] & 0xF0:
        problems.append("bad iNES header")
    vec = HEADER_BYTES + PRG_BYTES - 4  # reset vector at $FFFC
    reset = rom[vec] | rom[vec + 1] << 8 if len(rom) >= vec + 2 else 0
    if not 0xC000 <= reset < 0xFFFA:
        problems.append(f"bad reset vector ${reset:04X}")
    if problems:
        raise NesBuildError("The baked game didn't come out right.", "; ".join(problems))
