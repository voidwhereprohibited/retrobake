"""Find RetroArch installs on Windows and Linux.

Everything here is read-only: we look for files, we never change anything.
All OS lookups are injectable so tests run with fake folders, never the real PC.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from .config import read_cfg, resolve_dir
from .cores import CoreInfo, find_core

FLATPAK_ID = "org.libretro.RetroArch"
STEAM_APP_ID = "1118310"


@dataclass
class RetroArchInstall:
    kind: str  # windows-installer | windows-portable | windows-steam | linux-native |
    # linux-flatpak | linux-snap | linux-appimage | linux-steam
    os_name: str  # "windows" | "linux"
    launch: tuple[str, ...]  # program (+ fixed args) to start RetroArch
    config_dir: Path
    cores_dirs: list[Path] = field(default_factory=list)
    playlists_dir: Path = Path()
    thumbnails_dir: Path = Path()
    exe_dir: Path | None = None

    @property
    def label(self) -> str:
        return _LABELS.get(self.kind, "RetroArch")

    def find_core(self, system: str) -> tuple[Path, CoreInfo] | None:
        return find_core(self.cores_dirs, system, self.os_name)


_LABELS = {
    "windows-installer": "RetroArch (installed)",
    "windows-portable": "RetroArch (portable folder)",
    "windows-steam": "RetroArch (Steam)",
    "linux-native": "RetroArch",
    "linux-flatpak": "RetroArch (Flatpak)",
    "linux-snap": "RetroArch (Snap)",
    "linux-appimage": "RetroArch (AppImage)",
    "linux-steam": "RetroArch (Steam)",
}


def current_os() -> str:
    return "windows" if sys.platform.startswith("win") else "linux"


def _finish(inst: RetroArchInstall, home: Path, default_cores: list[Path]) -> RetroArchInstall:
    """Fill cores/playlists/thumbnails from retroarch.cfg, falling back to defaults."""
    cfg = read_cfg(inst.config_dir / "retroarch.cfg")
    if inst.exe_dir and not cfg:
        cfg = read_cfg(inst.exe_dir / "retroarch.cfg")
    cores = resolve_dir(cfg.get("libretro_directory"), home=home, exe_dir=inst.exe_dir)
    dirs = ([cores] if cores else []) + default_cores
    seen: list[Path] = []
    for d in dirs:
        if d not in seen:
            seen.append(d)
    inst.cores_dirs = seen
    inst.playlists_dir = resolve_dir(
        cfg.get("playlist_directory"), home=home, exe_dir=inst.exe_dir
    ) or (inst.config_dir / "playlists")
    inst.thumbnails_dir = resolve_dir(
        cfg.get("thumbnails_directory"), home=home, exe_dir=inst.exe_dir
    ) or (inst.config_dir / "thumbnails")
    return inst


_VDF_PATH = re.compile(r'"path"\s+"([^"]+)"')


def steam_libraries(steam_roots: list[Path]) -> list[Path]:
    """Steam library folders (the main one plus any listed in libraryfolders.vdf)."""
    libs: list[Path] = []
    for root in steam_roots:
        if not root.is_dir():
            continue
        libs.append(root)
        vdf = root / "steamapps" / "libraryfolders.vdf"
        try:
            text = vdf.read_text(encoding="utf-8", errors="replace")[:200_000]
        except OSError:
            continue
        for raw in _VDF_PATH.findall(text):
            libs.append(Path(raw.replace("\\\\", "\\")))
    out: list[Path] = []
    for p in libs:
        if p not in out:
            out.append(p)
    return out


# ---------------------------------------------------------------- Linux


def _detect_linux(
    home: Path, env: Mapping[str, str], which: Callable[[str], str | None]
) -> list[RetroArchInstall]:
    found: list[RetroArchInstall] = []
    xdg = Path(env["XDG_CONFIG_HOME"]) if env.get("XDG_CONFIG_HOME") else home / ".config"
    user_cfg = xdg / "retroarch"
    system_cores = [
        Path("/usr/lib/x86_64-linux-gnu/libretro"),
        Path("/usr/lib/aarch64-linux-gnu/libretro"),
        Path("/usr/lib/libretro"),
        Path("/usr/lib64/libretro"),
    ]

    # Flatpak (most common on modern desktops, Steam Deck, etc.)
    flatpak_exports = [
        Path("/var/lib/flatpak/exports/bin") / FLATPAK_ID,
        home / ".local/share/flatpak/exports/bin" / FLATPAK_ID,
    ]
    flatpak = which("flatpak")
    if flatpak and any(p.exists() for p in flatpak_exports):
        cfg_dir = home / ".var/app" / FLATPAK_ID / "config/retroarch"
        found.append(
            _finish(
                RetroArchInstall("linux-flatpak", "linux", (flatpak, "run", FLATPAK_ID), cfg_dir),
                home,
                [cfg_dir / "cores"],
            )
        )

    # Native package (apt/dnf/pacman) - but /snap/bin/retroarch is the Snap
    native = which("retroarch")
    if native and not native.startswith("/snap/"):
        found.append(
            _finish(
                RetroArchInstall("linux-native", "linux", (native,), user_cfg),
                home,
                [user_cfg / "cores", *system_cores],
            )
        )

    # Snap
    snap_bin = Path("/snap/bin/retroarch")
    if snap_bin.exists() or (native and native.startswith("/snap/")):
        cfg_dir = home / "snap/retroarch/current/.config/retroarch"
        found.append(
            _finish(
                RetroArchInstall("linux-snap", "linux", (str(snap_bin),), cfg_dir),
                home,
                [cfg_dir / "cores"],
            )
        )

    # AppImage in the usual download/app folders
    for folder in ("Applications", "Downloads", "Desktop", ".local/bin", "bin", "Apps"):
        d = home / folder
        if not d.is_dir():
            continue
        for app in sorted(d.glob("RetroArch*.AppImage")):
            portable = Path(str(app) + ".home") / ".config/retroarch"
            cfg_dir = portable if portable.is_dir() else user_cfg
            found.append(
                _finish(
                    RetroArchInstall("linux-appimage", "linux", (str(app),), cfg_dir),
                    home,
                    [cfg_dir / "cores"],
                )
            )

    # Steam
    roots = [
        home / ".local/share/Steam",
        home / ".steam/steam",
        home / ".var/app/com.valvesoftware.Steam/.local/share/Steam",
        home / ".var/app/com.valvesoftware.Steam/data/Steam",
    ]
    seen_steam: set[Path] = set()
    for lib in steam_libraries(roots):
        ra = lib / "steamapps/common/RetroArch"
        exe = ra / "retroarch"
        if not exe.is_file():
            continue
        real = ra.resolve()
        if real in seen_steam:
            continue
        seen_steam.add(real)
        cfg_dir = ra if (ra / "retroarch.cfg").is_file() else user_cfg
        found.append(
            _finish(
                RetroArchInstall("linux-steam", "linux", (str(exe),), cfg_dir, exe_dir=ra),
                home,
                [ra / "cores"],
            )
        )
    return found


# ---------------------------------------------------------------- Windows


def _detect_windows(
    home: Path, env: Mapping[str, str], which: Callable[[str], str | None]
) -> list[RetroArchInstall]:
    found: list[RetroArchInstall] = []
    appdata = Path(env["APPDATA"]) if env.get("APPDATA") else home / "AppData/Roaming"
    drive = env.get("SystemDrive", "C:") + os.sep
    pf86 = Path(env.get("ProgramFiles(x86)", drive + "Program Files (x86)"))
    pf = Path(env.get("ProgramFiles", drive + "Program Files"))

    candidates: list[tuple[str, Path]] = [
        ("windows-installer", Path(drive) / "RetroArch-Win64"),
        ("windows-installer", Path(drive) / "RetroArch"),
        ("windows-installer", appdata / "RetroArch"),
        ("windows-portable", pf / "RetroArch"),
        ("windows-portable", home / "RetroArch"),
        ("windows-portable", home / "Desktop/RetroArch"),
        ("windows-portable", home / "Downloads/RetroArch"),
    ]
    on_path = which("retroarch")
    if on_path:
        candidates.append(("windows-portable", Path(on_path).parent))
    for lib in steam_libraries([pf86 / "Steam", pf / "Steam"]):
        candidates.append(("windows-steam", lib / "steamapps/common/RetroArch"))

    seen: list[Path] = []
    for kind, folder in candidates:
        exe = folder / "retroarch.exe"
        if not exe.is_file():
            continue
        key = Path(os.path.normcase(str(folder)))
        if key in seen:
            continue
        seen.append(key)
        # Windows looks for retroarch.cfg next to the .exe first, then %APPDATA%.
        cfg_dir = folder if (folder / "retroarch.cfg").is_file() else appdata
        found.append(
            _finish(
                RetroArchInstall(kind, "windows", (str(exe),), cfg_dir, exe_dir=folder),
                home,
                [folder / "cores"],
            )
        )
    return found


# ---------------------------------------------------------------- public


def detect(
    *,
    os_name: str | None = None,
    home: Path | None = None,
    env: Mapping[str, str] | None = None,
    which: Callable[[str], str | None] = shutil.which,
    extra_folders: list[Path] | None = None,
) -> list[RetroArchInstall]:
    """All RetroArch installs we can find, best first.

    extra_folders: folders the user picked by hand ("I keep RetroArch here").
    """
    os_name = os_name or current_os()
    home = home or Path.home()
    env = os.environ if env is None else env
    if os_name == "windows":
        found = _detect_windows(home, env, which)
    else:
        found = _detect_linux(home, env, which)
    for folder in extra_folders or []:
        exe = folder / ("retroarch.exe" if os_name == "windows" else "retroarch")
        if exe.is_file():
            cfg_dir = folder  # a hand-picked folder is treated as portable
            found.insert(
                0,
                _finish(
                    RetroArchInstall(
                        f"{os_name}-portable", os_name, (str(exe),), cfg_dir, exe_dir=folder
                    ),
                    home,
                    [folder / "cores"],
                ),
            )
    return found


def pick(installs: list[RetroArchInstall], system: str) -> RetroArchInstall | None:
    """The first install that already has a core for this system, else the first one."""
    for inst in installs:
        if inst.find_core(system):
            return inst
    return installs[0] if installs else None
