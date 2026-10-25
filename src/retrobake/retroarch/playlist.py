"""The "RetroBake" playlist and its box-art thumbnails.

The only files RetroBake writes inside RetroArch's folders are:
  <playlists>/RetroBake.lpl
  <thumbnails>/RetroBake/Named_Boxarts/<label>.png
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import unicodedata
from pathlib import Path

from .cores import CoreInfo
from .detect import RetroArchInstall

PLAYLIST_NAME = "RetroBake"
PLAYLIST_FILE = f"{PLAYLIST_NAME}.lpl"
MAX_LABEL = 64
MAX_COVER_BYTES = 4 * 1024 * 1024
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

# RetroArch replaces these with "_" when it looks for a thumbnail file.
_THUMB_BAD = re.compile(r'[&*/:`<>?\\|"]')


class PlaylistError(Exception):
    pass


def clean_label(name: str) -> str:
    """Safe display name: no control chars, single spaces, length-limited."""
    name = unicodedata.normalize("NFC", str(name))
    name = "".join(ch for ch in name if unicodedata.category(ch)[0] != "C")
    name = " ".join(name.split())[:MAX_LABEL].strip()
    return name or "My RetroBake Game"


def thumbnail_name(label: str) -> str:
    return _THUMB_BAD.sub("_", label) + ".png"


def _empty() -> dict:
    return {
        "version": "1.5",
        "default_core_path": "",
        "default_core_name": "",
        "label_display_mode": 0,
        "right_thumbnail_mode": 0,
        "left_thumbnail_mode": 0,
        "thumbnail_match_mode": 0,
        "sort_mode": 0,
        "items": [],
    }


def load(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _empty()
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        return _empty()
    return data


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".retrobake-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def add_game(
    install: RetroArchInstall,
    rom: Path,
    name: str,
    core_path: Path,
    core: CoreInfo,
    cover_png: bytes | Path | None = None,
) -> Path:
    """Add (or update) a game in RetroBake.lpl and copy its cover art. Returns playlist path."""
    label = clean_label(name)
    rom = Path(rom).resolve()
    lpl = install.playlists_dir / PLAYLIST_FILE
    data = load(lpl)
    entry = {
        "path": str(rom),
        "label": label,
        "core_path": str(core_path),
        "core_name": core.display_name,
        "crc32": "DETECT",
        "db_name": PLAYLIST_FILE,
    }
    items = [i for i in data["items"] if isinstance(i, dict) and i.get("path") != str(rom)]
    items.append(entry)
    data["items"] = items
    _write_atomic(lpl, (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    if cover_png is not None:
        save_cover(install, label, cover_png)
    return lpl


def remove_game(install: RetroArchInstall, rom: Path) -> None:
    lpl = install.playlists_dir / PLAYLIST_FILE
    if not lpl.exists():
        return
    data = load(lpl)
    rom_s = str(Path(rom).resolve())
    data["items"] = [i for i in data["items"] if isinstance(i, dict) and i.get("path") != rom_s]
    _write_atomic(lpl, (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))


def save_cover(install: RetroArchInstall, label: str, cover_png: bytes | Path) -> Path:
    data = Path(cover_png).read_bytes() if isinstance(cover_png, Path) else bytes(cover_png)
    if len(data) > MAX_COVER_BYTES:
        raise PlaylistError("cover art is too large")
    if not data.startswith(PNG_MAGIC):
        raise PlaylistError("cover art must be a PNG image")
    dest_dir = install.thumbnails_dir / PLAYLIST_NAME / "Named_Boxarts"
    dest = dest_dir / thumbnail_name(clean_label(label))
    _write_atomic(dest, data)
    return dest
