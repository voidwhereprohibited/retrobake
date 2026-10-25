"""Load the game-design catalog and the game-spec JSON Schema (both ship as package data)."""

from __future__ import annotations

import json
from functools import cache
from importlib import resources
from typing import Any

SPEC_VERSION = "1.0"


def _read_json(name: str) -> dict[str, Any]:
    return json.loads(resources.files(__package__).joinpath(name).read_text(encoding="utf-8"))


@cache
def catalog() -> dict[str, Any]:
    """Genres, modules, systems and all wizard choice lists, with plain-English labels."""
    return _read_json("catalog.json")


@cache
def schema() -> dict[str, Any]:
    """The game-spec JSON Schema (draft-07)."""
    return _read_json("game_spec.schema.json")


def system_limits(system: str) -> dict[str, Any]:
    return catalog()["systems"][system]


def genre_label(genre: str) -> str:
    return catalog()["genres"][genre]["label"]


def available_genres() -> list[str]:
    """Genres the engines can bake today, most popular first."""
    return [g for g, info in catalog()["genres"].items() if info["available"]]


def module_available(kind: str, module_id: str) -> bool:
    return bool(catalog()["modules"][kind][module_id]["available"])
