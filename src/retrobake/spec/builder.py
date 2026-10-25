"""Build a starting game-spec from the wizard's first screens (system, genres, description)."""

from __future__ import annotations

import secrets
from typing import Any

from .catalog import SPEC_VERSION, catalog
from .rules import Fix, resolve
from .style_refs import style_from_text


def combine_modules(genres: list[str]) -> dict[str, Any]:
    """Modules for one genre, or a mashup of two (first = primary feel)."""
    cat = catalog()
    if len(genres) == 1:
        mods = cat["genres"][genres[0]]["modules"]
    else:
        recipe = cat["mashup_recipes"].get("+".join(genres))
        if recipe:
            mods = recipe
        else:
            # Generic mashup: move/fight like the primary, world + extras from the secondary.
            a, b = (cat["genres"][g]["modules"] for g in genres)
            mods = {
                "movement": a["movement"],
                "combat": a["combat"],
                "progression": b["progression"],
                "extras": list(dict.fromkeys(b["extras"] + a["extras"])),
            }
    return {k: (list(v) if isinstance(v, list) else v) for k, v in mods.items()}


def new_spec(
    system: str,
    genres: list[str],
    description: str = "",
    title: str = "My Game",
    seed: int | None = None,
) -> tuple[dict[str, Any], list[Fix]]:
    """Starting spec with sensible defaults for every field, ready for the guided questions.

    Franchise references in ``description`` steer modules and style; the stored description has
    them replaced with neutral wording.
    """
    cat = catalog()
    hints = style_from_text(description)
    modules = combine_modules(genres)
    if len(genres) == 1 and hints.matched:
        # A single-genre game described "like X" takes X's module choices where they exist.
        for k in ("movement", "combat", "progression"):
            if k in hints.modules:
                modules[k] = hints.modules[k]

    primary = cat["genres"][genres[0]]["world"]
    secondary = cat["genres"][genres[-1]]["world"]
    world = {**secondary, **primary}
    spec: dict[str, Any] = {
        "spec_version": SPEC_VERSION,
        "system": system,
        "genres": list(genres),
        "title": title,
        "description": hints.clean_text,
        "hero": {"archetype": "knight" if modules["combat"] == "melee" else "explorer"},
        "modules": modules,
        "world": world,
        "style": {
            "palette_mood": hints.palette_mood or "bright",
            "music_mood": "heroic",
            "tags": hints.tags,
        },
        "seed": secrets.randbelow(2**32) if seed is None else seed,
    }
    return resolve(spec)
