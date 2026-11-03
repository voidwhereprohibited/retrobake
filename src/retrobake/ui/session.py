"""Shared state and helpers for the make-a-game screens (Describe .. Finish).

``Session`` holds the services the screens call (AI art/names, the ROM builders, RetroArch)
and what has been made so far (cover PNG, baked ROM path). Every service can be swapped, so
tests run the whole flow offline with no network and no real emulator.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QFileDialog

from retrobake import retroarch
from retrobake.ai.service import AIService, AISettings, CoverArt
from retrobake.security import safe_filename


class Task(QThread):
    """Runs ``fn()`` off the UI thread; emits ``done(result, error)`` back on the UI thread.

    Connect ``done`` to a bound method of a widget (not a lambda) so Qt delivers it on the
    UI thread.
    """

    done = Signal(object, object)

    def __init__(self, fn: Callable[[], Any], parent: Any = None) -> None:
        super().__init__(parent)
        self._fn = fn

    def run(self) -> None:
        try:
            result = self._fn()
        except Exception as exc:  # noqa: BLE001 - reported to the UI in plain English
            self.done.emit(None, exc)
        else:
            self.done.emit(result, None)


def default_work_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return base / "RetroBake" / "Games"
    base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "retrobake" / "games"


def error_text(exc: BaseException) -> str:
    """User-ready text for any error (builders and guards carry a plain-English ``message``)."""
    msg = getattr(exc, "message", "")
    return msg if isinstance(msg, str) and msg else "Something went wrong. Please try again."


def default_bake(spec: dict[str, Any], work_dir: Path) -> Path:
    """Validate the spec, bake with the right builder, write the ROM, return its path."""
    from retrobake import spec as gamespec

    errors = gamespec.validate(spec)
    if errors:
        raise ValueError("; ".join(errors))
    if spec["system"] == "snes":
        from retrobake.builders import snes

        rom, ext = snes.bake(spec).rom, ".sfc"
    else:
        from retrobake.builders import nes

        rom, ext = nes.bake(spec).rom, ".nes"
    work_dir.mkdir(parents=True, exist_ok=True)
    path = work_dir / safe_filename(spec["title"], ext)
    path.write_bytes(rom)
    return path


def ask_save_dialog(caption: str, default_name: str, file_filter: str) -> str | None:
    path, _ = QFileDialog.getSaveFileName(None, caption, default_name, file_filter)
    return path or None


@dataclass
class Session:
    ai: AIService = field(
        default_factory=lambda: AIService(
            AISettings(online=os.environ.get("RETROBAKE_OFFLINE") != "1")
        )
    )
    work_dir: Path = field(default_factory=default_work_dir)
    bake: Callable[[dict[str, Any], Path], Path] = default_bake
    detect: Callable[[], list] = retroarch.detect
    launcher: retroarch.Launcher = field(default_factory=retroarch.Launcher)
    ask_save: Callable[[str, str, str], str | None] = ask_save_dialog
    # Results of the steps:
    art: CoverArt | None = None
    cover_png: bytes | None = None
    rom_path: Path | None = None
    baked_key: str = ""

    def reset(self) -> None:
        self.art = None
        self.cover_png = None
        self.rom_path = None
        self.baked_key = ""
