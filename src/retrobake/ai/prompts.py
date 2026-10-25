"""Turn a game-spec into AI prompts.

Prompts are fixed templates in code. Spec choices are mapped through our own word tables (never
copied), and the only user text (story, hero description) goes through
``security.quote_user_text`` as quoted, length-limited data. ``check_prompt`` runs on the result.
The game title is never sent to the image model (it is drawn on afterwards by RetroBake).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from retrobake.security import check_prompt, quote_user_text

GENRE_WORDS = {
    "platformer": "side-scrolling platform action",
    "topdown_adventure": "top-down action adventure",
    "rpg": "fantasy role-playing adventure",
    "shooter": "space shooter action",
    "puzzle": "colorful puzzle game",
    "sports": "arcade sports",
}
SETTING_WORDS = {
    "grassland": "rolling green hills",
    "forest": "a deep enchanted forest",
    "castle": "a stone castle",
    "cave": "glowing crystal caves",
    "desert": "a sunny desert",
    "ocean": "a sparkling ocean",
    "ice": "icy snowy mountains",
    "volcano": "a fiery volcano",
    "city": "a neon city at night",
    "space": "outer space with planets",
    "haunted": "a spooky haunted manor",
    "sky": "floating islands above the clouds",
}
HERO_WORDS = {
    "knight": "a brave young knight",
    "explorer": "a daring explorer",
    "robot": "a friendly robot",
    "animal": "a heroic animal",
    "wizard": "a clever wizard",
    "kid": "a determined kid",
    "ninja": "a nimble ninja",
    "pilot": "an ace pilot",
}
MOOD_WORDS = {
    "bright": "bright",
    "pastel": "soft pastel",
    "warm": "warm",
    "earthy": "earthy",
    "icy": "cool icy",
    "neon": "vivid neon",
    "dark": "dark dramatic",
    "spooky": "spooky",
}
ERA = {"nes": "1980s 8-bit era", "snes": "early 1990s 16-bit era"}

_COVER = (
    "Retro {era} video game box art illustration, painted cover art, bold {mood} colors, "
    "dramatic heroic composition. Game type: {genre}. Setting: {setting}. "
    "Main hero: {hero}, details {hero_text}. Story idea {story}. "
    "Original characters only. No text, no letters, no logo, no watermark, no border."
)
NAMES_SYSTEM = (
    "You invent names for brand new retro video games. Reply with exactly 8 game titles, one per "
    "line, nothing else: no numbering, no quotes, no explanations. Each title has 1 to 4 words, "
    "at most 22 characters, using only English letters, numbers and spaces. Every title must be "
    "original: never use names of existing games, companies, characters or brands."
)
_NAMES = (
    "Name ideas for a {era} game. Game type: {genre}. Setting: {setting}. Hero: {hero}, details "
    "{hero_text}. Mood: {mood}. Story idea {story}."
)


@dataclass(frozen=True)
class Prompt:
    text: str
    system: str = ""


def _get(spec: dict[str, Any], *path: str) -> Any:
    node: Any = spec
    for key in path:
        node = node.get(key) if isinstance(node, dict) else None
    return node


def _slots(spec: dict[str, Any]) -> dict[str, str]:
    genres = [g for g in (_get(spec, "genres") or []) if g in GENRE_WORDS][:2]
    genre = " mixed with ".join(GENRE_WORDS[g] for g in genres) or GENRE_WORDS["platformer"]
    story = _get(spec, "description")
    hero_text = _get(spec, "hero", "description")
    return {
        "era": ERA.get(_get(spec, "system"), ERA["nes"]),
        "genre": genre,
        "setting": SETTING_WORDS.get(_get(spec, "world", "setting"), SETTING_WORDS["grassland"]),
        "hero": HERO_WORDS.get(_get(spec, "hero", "archetype"), HERO_WORDS["explorer"]),
        "mood": MOOD_WORDS.get(_get(spec, "style", "palette_mood"), MOOD_WORDS["bright"]),
        "story": _quoted(story, 240, '"an original adventure"'),
        "hero_text": _quoted(hero_text, 90, '"an original design"'),
    }


def _quoted(text: Any, max_len: int, empty: str) -> str:
    if not isinstance(text, str) or not text.strip():
        return empty
    return quote_user_text(text, max_len=max_len)


def cover_prompt(spec: dict[str, Any]) -> Prompt:
    """Image prompt for the cover art. Raises InputRejected only if the guard trips."""
    return Prompt(check_prompt(_COVER.format(**_slots(spec))))


def names_prompt(spec: dict[str, Any]) -> Prompt:
    """Text prompt (+ fixed system prompt) for name ideas."""
    return Prompt(check_prompt(_NAMES.format(**_slots(spec))), check_prompt(NAMES_SYSTEM))
