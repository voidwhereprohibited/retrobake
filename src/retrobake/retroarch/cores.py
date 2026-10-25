"""Which libretro cores RetroBake uses, in order of preference."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CoreInfo:
    file_stem: str  # e.g. "mesen_libretro"
    display_name: str  # shown in RetroArch's playlist + our UI
    downloader_name: str  # how it's labelled in RetroArch's Core Downloader


# Preference order per system. Mesen/bsnes = most accurate, the others = lighter.
CORES: dict[str, tuple[CoreInfo, ...]] = {
    "nes": (
        CoreInfo(
            "mesen_libretro", "Nintendo - NES / Famicom (Mesen)", "Nintendo - NES / Famicom (Mesen)"
        ),
        CoreInfo(
            "fceumm_libretro",
            "Nintendo - NES / Famicom (FCEUmm)",
            "Nintendo - NES / Famicom (FCEUmm)",
        ),
        CoreInfo(
            "nestopia_libretro",
            "Nintendo - NES / Famicom (Nestopia)",
            "Nintendo - NES / Famicom (Nestopia)",
        ),
    ),
    "snes": (
        CoreInfo(
            "snes9x_libretro",
            "Nintendo - SNES / SFC (Snes9x - Current)",
            "Nintendo - SNES / SFC (Snes9x - Current)",
        ),
        CoreInfo(
            "bsnes_libretro", "Nintendo - SNES / SFC (bsnes)", "Nintendo - SNES / SFC (bsnes)"
        ),
    ),
}

ROM_EXTENSIONS = {"nes": (".nes",), "snes": (".sfc", ".smc")}


def core_ext(os_name: str) -> str:
    return ".dll" if os_name == "windows" else ".so"


def find_core(cores_dirs: list[Path], system: str, os_name: str) -> tuple[Path, CoreInfo] | None:
    """First preferred core that exists in any of the cores folders, or None."""
    if system not in CORES:
        raise ValueError(f"unknown system: {system!r}")
    ext = core_ext(os_name)
    for info in CORES[system]:
        for d in cores_dirs:
            p = d / f"{info.file_stem}{ext}"
            if p.is_file():
                return p, info
    return None
