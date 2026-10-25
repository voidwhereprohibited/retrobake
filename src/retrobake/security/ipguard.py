"""IP guard: keep franchise, studio and character names out of everything RetroBake outputs.

Style words are fine ("cute", "jump_heavy"); names are not ("Mario", "Pok\u00e9mon").
Matching ignores case, accents, look-alike letters (Cyrillic/Greek), simple leetspeak
and spacing ("M a r i o", "Mar1o", "SuperMario", "Nintendo64").
The list lives in ip_blocklist.json; game-design's style_refs table is the first pass and
this module is the final gate before titles, menus, AI prompts and ROM text.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources

from .errors import InputRejected

_TOKEN = re.compile(r"[\w@$]+")
_FOLD = str.maketrans(
    {
        # Cyrillic look-alikes
        "\u0430": "a", "\u0435": "e", "\u043e": "o", "\u0440": "p", "\u0441": "c",
        "\u0443": "y", "\u0445": "x", "\u043a": "k", "\u043c": "m", "\u0442": "t",
        "\u043d": "h", "\u0432": "b", "\u0456": "i", "\u0458": "j", "\u0455": "s",
        "\u0501": "d", "\u0261": "g", "\u04cf": "l",
        # Greek look-alikes
        "\u03b1": "a", "\u03bf": "o", "\u03b5": "e", "\u03b9": "i", "\u03ba": "k",
        "\u03bd": "v", "\u03c1": "p", "\u03c4": "t", "\u03c5": "u", "\u03c7": "x",
        # leetspeak
        "0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "8": "b",
        "@": "a", "$": "s", "_": None,
    }
)
_MAX_WINDOW = 12
_PREFIX_MIN = 6
TITLE_MESSAGE = (
    "That name is too close to an existing game, company or character. "
    "Try an original name of your own!"
)
NEUTRAL = "a classic game"


def fold(token: str) -> str:
    """Fold one token to a plain a-z0-9 matching key."""
    text = unicodedata.normalize("NFKD", unicodedata.normalize("NFKC", token))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).casefold()
    return re.sub(r"[^a-z0-9]", "", text.translate(_FOLD))


@dataclass(frozen=True)
class _Lists:
    strong: dict[str, str]  # compact key -> term
    ambiguous: dict[str, str]
    allow: frozenset[str]


def _compact(term: str) -> str:
    return "".join(fold(t) for t in _TOKEN.findall(term))


@lru_cache(maxsize=1)
def _lists() -> _Lists:
    raw = json.loads(
        resources.files(__package__).joinpath("ip_blocklist.json").read_text(encoding="utf-8")
    )
    return _Lists(
        strong={_compact(t): t for t in raw["terms"]},
        ambiguous={_compact(t): t for t in raw.get("ambiguous", [])},
        allow=frozenset(_compact(t) for t in raw.get("allow", [])),
    )


def _lookup(key: str, table: dict[str, str], prefix: bool) -> str | None:
    if key in table:
        return table[key]
    for stem in (key[:-1], key[:-2]) if key.endswith("s") else ():
        if len(stem) >= 4 and stem in table:
            return table[stem]
    if prefix:
        for k, term in table.items():
            if len(k) >= _PREFIX_MIN and (key.startswith(k) or key.endswith(k)):
                return term
    return None


def _scan(text: str) -> list[tuple[int, int, str, bool]]:
    """Return (start, end, term, is_strong) spans, longest match first, no overlaps."""
    lists = _lists()
    toks = [(m.start(), m.end(), fold(m.group())) for m in _TOKEN.finditer(text)]
    toks = [t for t in toks if t[2]]
    hits: list[tuple[int, int, str, bool]] = []
    i = 0
    while i < len(toks):
        found = None
        for n in range(min(_MAX_WINDOW, len(toks) - i), 0, -1):
            key = "".join(t[2] for t in toks[i : i + n])
            if key in lists.allow:
                found = (n, None, False)
                break
            single = n == 1
            term = _lookup(key, lists.strong, prefix=single)
            if term:
                found = (n, term, True)
                break
            term = _lookup(key, lists.ambiguous, prefix=False)
            if term:
                found = (n, term, False)
                break
        if found is None:
            i += 1
            continue
        n, term, strong = found
        if term:
            hits.append((toks[i][0], toks[i + n - 1][1], term, strong))
        i += n
    return hits


def _active(hits: list[tuple[int, int, str, bool]], strict: bool) -> list[tuple[int, int, str]]:
    if strict or any(h[3] for h in hits):
        return [h[:3] for h in hits]
    return []


def find_ip(text: str, *, strict: bool = False) -> list[str]:
    """Names found in ``text`` (unique, in order). ``strict`` also flags everyday-word names."""
    seen: list[str] = []
    for _, _, term in _active(_scan(text), strict):
        if term not in seen:
            seen.append(term)
    return seen


def scrub_ip(text: str, replacement: str = NEUTRAL) -> tuple[str, list[str]]:
    """Replace names in free text (descriptions, AI prompts). Returns (clean_text, terms)."""
    spans = _active(_scan(text), strict=False)
    for start, end, _ in reversed(spans):
        text = text[:start] + replacement + text[end:]
    terms: list[str] = []
    for _, _, t in spans:
        if t not in terms:
            terms.append(t)
    return re.sub(r"\s{2,}", " ", text).strip(), terms


def check_title(title: str, field: str = "title") -> str:
    """Titles and name ideas may not contain any listed name. Raises InputRejected."""
    if find_ip(title, strict=True):
        raise InputRejected(field, TITLE_MESSAGE)
    return title
