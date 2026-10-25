"""Read-only parsing of retroarch.cfg.

RetroBake never writes to retroarch.cfg. We only read a few directory keys so we
know where cores, playlists and thumbnails live.
"""

from __future__ import annotations

import re
from pathlib import Path

_LINE = re.compile(r'^\s*([A-Za-z0-9_]+)\s*=\s*"?(.*?)"?\s*$')
_MAX_CFG_BYTES = 2 * 1024 * 1024  # a real retroarch.cfg is ~100 KB

KEYS = ("libretro_directory", "playlist_directory", "thumbnails_directory")


def read_cfg(path: Path) -> dict[str, str]:
    """Return the key/value pairs in a retroarch.cfg. Missing or unreadable -> {}."""
    try:
        if path.stat().st_size > _MAX_CFG_BYTES:
            return {}
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    out: dict[str, str] = {}
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        m = _LINE.match(line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def resolve_dir(value: str | None, *, home: Path, exe_dir: Path | None) -> Path | None:
    """Turn a retroarch.cfg directory value into a real path.

    Handles "", "default" (meaning: use RetroArch's built-in default), "~" (home) and
    ":" (relative to the folder holding the RetroArch program, used by portable installs).
    """
    if not value or value == "default":
        return None
    if value.startswith("~"):
        return home / value[1:].lstrip("/\\")
    if value.startswith(":"):
        if exe_dir is None:
            return None
        return exe_dir / value[1:].lstrip("/\\")
    return Path(value)
