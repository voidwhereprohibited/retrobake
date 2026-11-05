"""The ai-service contract: cover art + name ideas, made offline on the user's PC.

RetroBake needs no account, key or online AI (Roger, 11/01: "No AI"). Covers and names come
from the deterministic offline generator in ``offline.py``; nothing here touches the network.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from retrobake.security import OutputRejected, check_title, sanitize, validate_name

from . import offline
from .font import add_title_banner
from .raster import Canvas, from_png

Source = Literal["offline"]
MAX_NAME_CHARS = 24  # longest name idea we offer
MIN_NAME_CHARS = 3
_NUMBERING = re.compile(r"^\s*(?:[-*\u2022]+|\(?\d{1,2}[.):\]]|[a-hA-H][.)])\s*")


@dataclass(frozen=True)
class CoverArt:
    png: bytes  # the picture without the title, PNG, exactly width x height
    width: int
    height: int
    source: Source = "offline"
    message: str = ""


@dataclass(frozen=True)
class NameIdeas:
    names: list[str]
    source: Source = "offline"
    message: str = ""


def cover_size(spec: dict[str, Any]) -> tuple[int, int]:
    return offline.COVER_SIZE.get(spec.get("system"), offline.COVER_SIZE["nes"])


class AIService:
    """Cover art and name ideas. Fast, deterministic and offline; safe to call from any thread."""

    def make_art(self, spec: dict[str, Any], *, variant: int = 0) -> CoverArt:
        """Cover picture (no title). ``variant`` gives a different picture for "try another"."""
        canvas = offline.offline_art(spec, variant=variant)
        return CoverArt(canvas.to_png(), canvas.width, canvas.height)

    @staticmethod
    def with_title(art: CoverArt | bytes, title: str) -> bytes:
        """Final cover PNG with the game title banner. Raises InputRejected for a bad title."""
        clean = check_title(sanitize("title", title), field="title")
        png = art.png if isinstance(art, CoverArt) else art
        canvas: Canvas = from_png(png)
        add_title_banner(canvas, clean, bg=(12, 12, 28), fg=(252, 236, 160), shadow=(0, 0, 0))
        return canvas.to_png()

    def cover(
        self, spec: dict[str, Any], title: str, *, variant: int = 0
    ) -> tuple[bytes, CoverArt]:
        art = self.make_art(spec, variant=variant)
        return self.with_title(art, title), art

    def suggest_names(self, spec: dict[str, Any], n: int = 6, *, variant: int = 0) -> NameIdeas:
        """``n`` (1-12) original name ideas. The user can always type their own instead."""
        n = max(1, min(12, n))
        return NameIdeas(offline.offline_names(spec, n, variant=variant))


def parse_names(lines: object) -> list[str]:
    """Validated, de-duplicated names from free-text lines (anything bad is dropped)."""
    if not isinstance(lines, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for raw in lines[:40]:
        if not isinstance(raw, str):
            continue
        line = _NUMBERING.sub("", raw).strip().strip("\"'*`").strip()
        if not line or len(line) > MAX_NAME_CHARS:  # never truncate a name into something else
            continue
        try:
            name = validate_name(line)
        except OutputRejected:
            continue
        if len(name) < MIN_NAME_CHARS or name.casefold() in seen:
            continue
        seen.add(name.casefold())
        out.append(name)
    return out
