"""Offline prompt helper: a game description in plain words -> one template, one theme, a title.

Everything is local and deterministic (no network, no AI). The pipeline is:
lowercase -> tokenize -> stem -> join bigrams ("top down" -> "top_down") -> lexicon lookup ->
template scoring -> pick ONE template and ONE theme -> plan -> title.

Word lists, templates and title words live in ``lexicon.json``.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from functools import cache
from importlib import resources
from typing import Any

NEGATIONS = frozenset({"no", "not", "without", "never", "dont", "don't"})
BANNED_TITLE_WORDS = frozenset({"super", "mega", "ultra", "meets", "vs", "versus"})
BANNED_SUFFIXES = ("tron", "ster", "ville")
TITLE_FILLERS = frozenset({"The", "of", "the"})
MAX_TITLE_CHARS = 20
MAX_TITLE_WORDS = 4
TITLE_TRIES = 8
PATTERNS = ("{adj} {noun}", "The {adj} {noun}", "{noun} of the {place}", "The {noun}")

# Helper words -> game-spec values (the spec has fewer settings and heroes than the lexicon).
SPEC_SETTING = {"snow": "ice", "factory": "city"}
SPEC_HERO = {"racer": "pilot", "athlete": "kid"}
PALETTE = {
    "forest": "earthy", "cave": "dark", "castle": "earthy", "space": "neon", "ocean": "pastel",
    "desert": "warm", "city": "neon", "snow": "icy", "volcano": "warm", "haunted": "spooky",
    "sky": "bright", "factory": "dark",
}  # fmt: skip
MUSIC = {
    "heroic": "heroic", "dark": "mysterious", "cute": "upbeat", "comic": "upbeat",
    "tense": "tense", "mystic": "mysterious",
}  # fmt: skip


@cache
def lexicon() -> dict[str, Any]:
    text = resources.files(__package__).joinpath("lexicon.json").read_text(encoding="utf-8")
    return json.loads(text)


def stem(word: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            if suffix == "es" and not word[:-2].endswith(("s", "x", "z", "ch", "sh")):
                continue
            return word[: -len(suffix)]
    return word


def tokens(text: str) -> list[str]:
    """Stemmed words with negated ones dropped and two-word phrases joined."""
    words = re.findall(r"[a-z']+", text.lower().replace("-", " "))
    out: list[str] = []
    skip = False
    for w in words:
        if w in NEGATIONS:
            skip = True
            continue
        if not skip:
            out.append(stem(w.strip("'")))
        skip = False
    joined: list[str] = []
    for i, word in enumerate(out):
        joined.append(word)
        if i + 1 < len(out):
            joined.append(f"{word}_{out[i + 1]}")
    return joined


@cache
def _lookup() -> dict[str, dict[str, str]]:
    """category -> {stemmed word: canonical id}."""
    table: dict[str, dict[str, str]] = {}
    for cat in ("setting", "hero", "enemy", "verb", "tone", "goal"):
        words: dict[str, str] = {}
        for canon, syns in lexicon()[cat].items():
            for w in (canon, *syns):
                words.setdefault(stem(w), canon)
        table[cat] = words
    return table


def _found(cat: str, toks: list[str]) -> list[str]:
    """Canonical ids of ``cat`` in order of first mention, no repeats."""
    words = _lookup()[cat]
    return list(dict.fromkeys(words[t] for t in toks if t in words))


def _a(noun: str) -> str:
    return f"{'an' if noun[0].lower() in 'aeiou' else 'a'} {noun.lower()}"


@dataclass(frozen=True)
class Plan:
    template: str
    template_name: str
    genre: str
    theme: str
    hero: str
    enemies: list[str]
    verbs: list[str]
    tone: str
    goal: str
    palette_id: str
    music_mood: str
    title: str
    scores: dict[str, int] = field(default_factory=dict, compare=False)

    def summary(self) -> str:
        """A short, friendly description of what RetroBake understood."""
        enemies = " and ".join(f"{e}s" for e in self.enemies)
        return (
            f"{_a(self.template_name).capitalize()} set in {_a(self.theme)} world. "
            f"You play {_a(self.hero)} facing {enemies}. Goal: {self.goal}. "
            f"Mood: {self.tone}. Working title: {self.title}."
        )


def _score(tpl: dict[str, Any], seen: set[str], first: dict[str, int]) -> tuple[int, int, bool]:
    score, earliest = 0, 10**6
    for weight, signals in ((3, tpl["strong"]), (1, tpl["weak"])):
        for sig in signals:
            parts = sig.split("+")
            if all(p in seen for p in parts):
                score += weight
                earliest = min(earliest, *(first[p] for p in parts))
    explicit = any(w in seen for w in tpl["genre_words"])
    if explicit:
        score += 2
    return score, earliest, explicit


def pick_template(toks: list[str], genre: str | None = None) -> tuple[dict[str, Any], dict]:
    """Exactly one template. Ties: explicit genre word, then earliest signal, then list order."""
    canon = [c for cat in ("setting", "hero", "enemy", "verb") for c in _found(cat, toks)]
    first: dict[str, int] = {}
    for i, t in enumerate(toks):
        first.setdefault(t, i)
        for cat in ("setting", "hero", "enemy", "verb"):
            c = _lookup()[cat].get(t)
            if c:
                first.setdefault(c, i)
    seen = set(toks) | set(canon)
    templates = [t for t in lexicon()["templates"] if genre in (None, t["genre"])]
    if not templates:
        templates = lexicon()["templates"][:1]
    scored = [(t, *_score(t, seen, first)) for t in templates]
    best = min(
        enumerate(scored), key=lambda item: (-item[1][1], not item[1][3], item[1][2], item[0])
    )[1]
    scores = {t["id"]: s for t, s, _, _ in scored}
    if best[1] == 0:
        return templates[0], scores
    return best[0], scores


def pick_theme(toks: list[str]) -> str:
    words = _lookup()["setting"]
    counts: dict[str, int] = {}
    for t in toks:
        if t in words:
            counts[words[t]] = counts.get(words[t], 0) + 1
    if not counts:
        return lexicon()["defaults"]["setting"]
    top = max(counts.values())
    return next(s for s in counts if counts[s] == top)  # dicts keep first-mention order


def _seed(text: str) -> int:
    norm = " ".join(re.findall(r"[a-z0-9]+", text.lower()))
    return int.from_bytes(hashlib.sha256(norm.encode()).digest()[:8], "big")


def title_ok(title: str, theme: str) -> bool:
    bank = lexicon()["title_words"][theme]
    allowed = set(bank["adj"]) | set(bank["noun"]) | set(bank["place"]) | TITLE_FILLERS
    genre_words = {w for t in lexicon()["templates"] for w in t["genre_words"]}
    words = title.split()
    if not 1 <= len(words) <= MAX_TITLE_WORDS or len(title) > MAX_TITLE_CHARS:
        return False
    if not title.isascii() or not re.fullmatch(r"[A-Za-z ]+", title):
        return False
    for w in words:
        low = w.lower()
        if w not in allowed or low in BANNED_TITLE_WORDS or stem(low) in genre_words:
            return False
        if low.endswith(BANNED_SUFFIXES) or (w != w.capitalize() and w not in TITLE_FILLERS):
            return False
    if len(set(words) - TITLE_FILLERS) != len([w for w in words if w not in TITLE_FILLERS]):
        return False  # no repeated words ("Grove of the Grove")
    from retrobake.security import InputRejected, check_title

    try:
        check_title(title)
    except InputRejected:
        return False
    return True


def make_title(description: str, theme: str) -> str:
    """Deterministic title built only from the theme's word bank."""
    bank = lexicon()["title_words"][theme]
    seed = _seed(description)
    for attempt in range(TITLE_TRIES):
        n = seed + attempt * 7919
        pattern = PATTERNS[n % len(PATTERNS)]
        title = pattern.format(
            adj=bank["adj"][(n // 4) % len(bank["adj"])],
            noun=bank["noun"][(n // 32) % len(bank["noun"])],
            place=bank["place"][(n // 256) % len(bank["place"])],
        )
        if title_ok(title, theme):
            return title
    return f"The {bank['noun'][0]}"


def _consistent(found: list[str], allowed: list[str], limit: int) -> list[str]:
    kept = [x for x in found if x in allowed][:limit]
    return kept or allowed[:1]


def analyze(description: str, genre: str | None = None) -> Plan:
    """Read ``description`` and pick one template (of ``genre`` when given) and one theme."""
    toks = tokens(description)
    tpl, scores = pick_template(toks, genre)
    theme = pick_theme(toks)
    compat = lexicon()["compat"][theme]
    defaults = lexicon()["defaults"]
    tone = (_found("tone", toks) or [defaults["tone"]])[0]
    return Plan(
        template=tpl["id"],
        template_name=tpl["name"],
        genre=tpl["genre"],
        theme=theme,
        hero=_consistent(_found("hero", toks), compat["hero"], 1)[0],
        enemies=_consistent(_found("enemy", toks), compat["enemy"], 3),
        verbs=_found("verb", toks)[:3],
        tone=tone,
        goal=(_found("goal", toks) or [defaults["goal"]])[0],
        palette_id=PALETTE[theme],
        music_mood=MUSIC[tone],
        title=make_title(description, theme),
        scores=scores,
    )


def spec_defaults(plan: Plan) -> dict[str, dict[str, str]]:
    """Game-spec values the plan pre-fills (the wizard's question defaults)."""
    return {
        "hero": {"archetype": SPEC_HERO.get(plan.hero, plan.hero)},
        "world": {"setting": SPEC_SETTING.get(plan.theme, plan.theme)},
        "style": {"palette_mood": plan.palette_id, "music_mood": plan.music_mood},
    }
