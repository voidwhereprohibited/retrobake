"""Turn franchise references in user text ("like Zelda meets Mario") into style and module hints.

The franchise names below are used ONLY to recognise what the user typed. They never appear in
anything RetroBake outputs: the result carries generic genres, modules and style tags only, and
``clean_text`` has every recognised name replaced with a neutral phrase. The security agent's
IP guard is the final gate; this table is its first input.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Generic style vocabulary allowed in spec["style"]["tags"].
STYLE_TAGS = frozenset(
    {
        "bright",
        "cheerful",
        "cute",
        "fantasy",
        "sci_fi",
        "gothic",
        "spooky",
        "military",
        "robots",
        "ninja",
        "jump_heavy",
        "fast_paced",
        "exploration",
        "sword_and_shield",
        "boss_rush",
        "power_ups",
        "creature_collecting",
        "puzzle_blocks",
        "dark",
        "lonely",
        "arcade",
        "heroic_quest",
        "pastel",
        "whip",
    }
)

_NEUTRAL = "a classic game"


@dataclass(frozen=True)
class _Ref:
    genre: str
    modules: dict[str, Any] = field(default_factory=dict)
    tags: tuple[str, ...] = ()
    palette: str | None = None


# key: lowercase alias as typed by users.
_REFS: dict[str, _Ref] = {}


def _add(aliases: tuple[str, ...], ref: _Ref) -> None:
    for a in aliases:
        _REFS[a] = ref


_add(
    ("mario", "super mario", "mario bros"),
    _Ref(
        "platformer",
        {"movement": "side_jump", "combat": "stomp", "progression": "linear_levels"},
        ("bright", "cheerful", "jump_heavy", "power_ups"),
        "bright",
    ),
)
_add(
    ("zelda", "legend of zelda"),
    _Ref(
        "topdown_adventure",
        {"movement": "topdown_walk", "combat": "melee", "progression": "dungeons_items"},
        ("fantasy", "sword_and_shield", "exploration", "heroic_quest"),
        "earthy",
    ),
)
_add(
    ("metroid",),
    _Ref(
        "platformer",
        {"movement": "side_jump", "combat": "projectile", "progression": "open_map"},
        ("sci_fi", "dark", "lonely", "exploration"),
        "dark",
    ),
)
_add(
    ("mega man", "megaman", "rockman"),
    _Ref(
        "platformer",
        {"movement": "side_jump", "combat": "projectile", "progression": "linear_levels"},
        ("robots", "boss_rush", "sci_fi"),
        "bright",
    ),
)
_add(
    ("castlevania",),
    _Ref(
        "platformer",
        {"movement": "side_jump", "combat": "melee", "progression": "linear_levels"},
        ("gothic", "spooky", "whip"),
        "spooky",
    ),
)
_add(
    ("sonic", "sonic the hedgehog"),
    _Ref(
        "platformer",
        {"movement": "side_jump", "combat": "stomp", "progression": "linear_levels"},
        ("fast_paced", "bright", "jump_heavy"),
        "bright",
    ),
)
_add(
    ("kirby",),
    _Ref(
        "platformer",
        {"movement": "side_jump", "progression": "linear_levels"},
        ("cute", "pastel", "cheerful"),
        "pastel",
    ),
)
_add(
    ("donkey kong",),
    _Ref(
        "platformer",
        {"movement": "side_jump", "combat": "stomp", "progression": "linear_levels"},
        ("jump_heavy", "arcade"),
        "warm",
    ),
)
_add(
    ("ninja gaiden",),
    _Ref(
        "platformer",
        {"movement": "side_jump", "combat": "melee", "progression": "linear_levels"},
        ("ninja", "fast_paced", "dark"),
        "dark",
    ),
)
_add(
    ("contra",),
    _Ref(
        "platformer",
        {"movement": "side_jump", "combat": "projectile", "progression": "linear_levels"},
        ("military", "fast_paced", "arcade"),
        "earthy",
    ),
)
_add(
    ("gradius", "r-type", "galaga"),
    _Ref(
        "shooter",
        {"movement": "free_flight", "combat": "projectile", "progression": "linear_levels"},
        ("sci_fi", "arcade", "power_ups"),
        "neon",
    ),
)
_add(
    ("final fantasy", "dragon quest", "dragon warrior", "earthbound", "chrono trigger"),
    _Ref(
        "rpg",
        {"movement": "topdown_walk", "progression": "open_map"},
        ("fantasy", "heroic_quest", "exploration"),
        "warm",
    ),
)
_add(
    ("pokemon", "pokémon"),
    _Ref(
        "rpg",
        {"movement": "topdown_walk", "progression": "open_map"},
        ("creature_collecting", "cute", "exploration"),
        "bright",
    ),
)
_add(
    ("tetris", "dr. mario", "dr mario"),
    _Ref("puzzle", {"combat": "none"}, ("puzzle_blocks", "arcade"), "neon"),
)

_PATTERN = re.compile(
    r"(?<![\w])("
    + "|".join(re.escape(k) for k in sorted(_REFS, key=len, reverse=True))
    + r")(?![\w])",
    re.IGNORECASE,
)


@dataclass
class StyleHints:
    """Franchise-free result of reading the user's description."""

    genres: list[str] = field(default_factory=list)  # in the order mentioned, deduplicated
    modules: dict[str, Any] = field(default_factory=dict)  # suggestions; first mention wins
    tags: list[str] = field(default_factory=list)
    palette_mood: str | None = None
    clean_text: str = ""
    matched: int = 0


def style_from_text(text: str) -> StyleHints:
    """Read franchise references out of ``text``. Pure function, no I/O; ``text`` is data only."""
    hints = StyleHints()
    for match in _PATTERN.finditer(text):
        ref = _REFS[match.group(1).lower()]
        hints.matched += 1
        if ref.genre not in hints.genres:
            hints.genres.append(ref.genre)
        for k, v in ref.modules.items():
            hints.modules.setdefault(k, v)
        for t in ref.tags:
            if t not in hints.tags:
                hints.tags.append(t)
        hints.palette_mood = hints.palette_mood or ref.palette
    hints.clean_text = _PATTERN.sub(_NEUTRAL, text)
    return hints
