"""Build a starting game-spec from the wizard's first screens (system, genre, description).

A game has exactly one genre. Its modules and world come from that genre alone (or from a named
template such as "action-adventure"). Optional ``inspirations`` are other genres the user likes;
they are stored for engines to fine-tune feel (speeds, jump height) and never change the genre,
modules, world or names.
"""

from __future__ import annotations

import copy
import secrets
from typing import Any

from retrobake.security import scrub_ip

from . import helper
from .catalog import SPEC_VERSION, catalog
from .rules import Fix, resolve
from .style_refs import style_from_text


def genre_modules(genre: str, template: str | None = None) -> dict[str, Any]:
    """Starting modules for one genre, or for a named template of that genre."""
    cat = catalog()
    if template is not None:
        mods = cat["templates"][template]["modules"]
    else:
        mods = cat["genres"][genre]["modules"]
    return copy.deepcopy(mods)


def new_spec(
    system: str,
    genre: str,
    description: str = "",
    title: str = "",
    seed: int | None = None,
    *,
    inspirations: list[str] | tuple[str, ...] = (),
    template: str | None = None,
) -> tuple[dict[str, Any], list[Fix]]:
    """Starting spec with sensible defaults for every field, ready for the guided questions.

    Franchise references in ``description`` steer modules and style; the stored description has
    them replaced with neutral wording. The offline prompt helper reads the description and
    pre-fills the hero, setting, colors, music and (when ``title`` is empty) the title.
    """
    if not isinstance(genre, str):
        raise TypeError("a game has exactly one genre; pass it as a string")
    cat = catalog()
    if template is not None and cat["templates"][template]["genre"] != genre:
        raise ValueError(f"template {template!r} is a {cat['templates'][template]['genre']} game")

    hints = style_from_text(description)
    modules = genre_modules(genre, template)
    if hints.genres == [genre] and template is None:
        # "A platformer like X" takes X's module choices, but only when X is the same genre.
        for k in ("movement", "combat", "progression"):
            if k in hints.modules:
                modules[k] = hints.modules[k]

    spec: dict[str, Any] = {
        "spec_version": SPEC_VERSION,
        "system": system,
        "genres": [genre],
        "title": title,
        "description": scrub_ip(hints.clean_text)[0],
        "hero": {"archetype": "knight" if modules["combat"] == "melee" else "explorer"},
        "modules": modules,
        "world": dict(cat["genres"][genre]["world"]),
        "style": {
            "palette_mood": hints.palette_mood or "bright",
            "music_mood": "heroic",
            "tags": hints.tags,
        },
        "seed": secrets.randbelow(2**32) if seed is None else seed,
    }
    clean = spec["description"]
    if clean.strip():
        plan = helper.analyze(clean, genre)
        for section, values in helper.spec_defaults(plan).items():
            spec[section].update(values)
        spec["title"] = title or plan.title
    spec["title"] = spec["title"] or "My Game"
    extra = [g for g in dict.fromkeys(inspirations) if g != genre]
    if extra:
        spec["inspirations"] = extra
    return resolve(spec)
