"""What the wizard has made so far, shared by every screen."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from retrobake.builders.nes import NesRom


def _default_baker(spec: dict[str, Any]) -> NesRom:
    from retrobake.builders import nes

    return nes.bake(spec)


@dataclass
class Session:
    system: str = "nes"
    genre: str = "platformer"
    inspirations: list[str] = field(default_factory=list)
    description: str = ""
    spec: dict[str, Any] = field(default_factory=dict)  # the validated game-spec
    cover_png: bytes = b""
    rom: NesRom | None = None
    baker: Callable[[dict[str, Any]], NesRom] = _default_baker
