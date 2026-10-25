"""RetroArch integration: find it, Play Now, the RetroBake playlist, setup help.

Public API (the `retroarch` contract):
    detect(...) -> list[RetroArchInstall]        find installs, best first (read-only)
    pick(installs, system) -> RetroArchInstall    one that has a core for "nes"/"snes"
    advise(installs, system, os_name) -> SetupAdvice   plain-English setup help
    Launcher().play / relaunch / stop             Play Now + rebake-and-relaunch
    add_game(install, rom, name, core_path, core, cover_png)   RetroBake.lpl + box art
"""

from .cores import CORES, ROM_EXTENSIONS, CoreInfo
from .detect import RetroArchInstall, current_os, detect, pick
from .launch import Launcher, LaunchError, LaunchPlan, plan_launch
from .playlist import (
    PLAYLIST_FILE,
    PlaylistError,
    add_game,
    clean_label,
    remove_game,
    save_cover,
    thumbnail_name,
)
from .setup_helper import Action, SetupAdvice, advise

__all__ = [
    "CORES",
    "PLAYLIST_FILE",
    "ROM_EXTENSIONS",
    "Action",
    "CoreInfo",
    "LaunchError",
    "LaunchPlan",
    "Launcher",
    "PlaylistError",
    "RetroArchInstall",
    "SetupAdvice",
    "add_game",
    "advise",
    "clean_label",
    "current_os",
    "detect",
    "pick",
    "plan_launch",
    "remove_game",
    "save_cover",
    "thumbnail_name",
]
