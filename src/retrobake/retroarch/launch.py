"""Play Now: start RetroArch with the right core and the freshly baked ROM.

Security: arguments go to the OS as a list (never through a shell), the ROM must be
an existing file with a ROM extension, and the core must be inside the install's
cores folder.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from .cores import ROM_EXTENSIONS, CoreInfo
from .detect import RetroArchInstall


class LaunchError(Exception):
    """Something the user needs to fix. The message is plain English."""


@dataclass(frozen=True)
class LaunchPlan:
    argv: tuple[str, ...]
    core_path: Path
    core: CoreInfo
    rom: Path


def plan_launch(install: RetroArchInstall, rom: Path, system: str) -> LaunchPlan:
    rom = Path(rom)
    if system not in ROM_EXTENSIONS:
        raise LaunchError(f"RetroBake can't play {system!r} games yet.")
    if rom.suffix.lower() not in ROM_EXTENSIONS[system]:
        raise LaunchError("That file doesn't look like a game made for this system.")
    if not rom.is_file():
        raise LaunchError("We couldn't find the game file. Try baking it again.")
    found = install.find_core(system)
    if not found:
        raise LaunchError("RetroArch is missing the part it needs to play this game.")
    core_path, core = found
    if not any(_inside(core_path, d) for d in install.cores_dirs):
        raise LaunchError("The RetroArch core is in an unexpected place.")
    argv = (*install.launch, "-L", str(core_path), str(rom.resolve()))
    return LaunchPlan(argv, core_path, core, rom.resolve())


def _inside(path: Path, folder: Path) -> bool:
    try:
        path.resolve().relative_to(folder.resolve())
        return True
    except (ValueError, OSError):
        return False


class Launcher:
    """Starts RetroArch and remembers only the process *we* started,
    so "Rebake and play again" can close it and start the new ROM."""

    def __init__(self, popen=subprocess.Popen) -> None:
        self._popen = popen
        self._proc = None

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def play(self, install: RetroArchInstall, rom: Path, system: str) -> LaunchPlan:
        plan = plan_launch(install, rom, system)
        try:
            self._proc = self._popen(  # noqa: S603 - fixed argv list, no shell
                list(plan.argv),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
            )
        except OSError as exc:
            raise LaunchError("RetroArch didn't start. Try opening it once by itself.") from exc
        return plan

    def stop(self, timeout: float = 5.0) -> None:
        if not self.running:
            return
        self._proc.terminate()
        try:
            self._proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            self._proc.wait(timeout=timeout)

    def relaunch(self, install: RetroArchInstall, rom: Path, system: str) -> LaunchPlan:
        """Rebake -> relaunch loop: check the new ROM first, then swap."""
        plan_launch(install, rom, system)  # fail before closing the old game
        self.stop()
        return self.play(install, rom, system)
