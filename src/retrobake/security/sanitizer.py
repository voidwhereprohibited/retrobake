"""Input cleanup for every piece of user text (stdlib only).

Pipeline: cap length -> NFKC -> drop control/format/private/unassigned chars (bidi
overrides, zero-width, NUL...) -> limit stacked accents -> collapse whitespace -> cap
length -> per-field allowlist. User text is data: never put it in a shell command,
file path or assembly source without going through this module.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from .errors import InputRejected

_DROP_CATEGORIES = frozenset({"Cc", "Cf", "Co", "Cs", "Cn"})
_MAX_MARKS = 2  # combining marks kept per base letter (stops "zalgo" text)
_SPACES = re.compile(r"[ \t\u00a0]+")
_MANY_NEWLINES = re.compile(r"\n{3,}")
_ASCII_PUNCT = str.maketrans(
    {"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u2013": "-", "\u2014": "-"}
)


@dataclass(frozen=True)
class FieldRule:
    max_len: int
    multiline: bool = False
    ascii_only: bool = False
    pattern: str | None = None
    hint: str = ""
    min_len: int = 0


_TITLE_HINT = "Use letters, numbers, spaces and simple punctuation (. , ! ? ' & : -)."

# Keep in step with src/retrobake/spec/game_spec.schema.json (game-design contract).
FIELDS: dict[str, FieldRule] = {
    "title": FieldRule(
        24,
        ascii_only=True,
        min_len=1,
        hint=_TITLE_HINT,
        pattern=r"[A-Za-z0-9][A-Za-z0-9 .,!?'&:-]*",
    ),
    "name_idea": FieldRule(
        24,
        ascii_only=True,
        min_len=1,
        hint=_TITLE_HINT,
        pattern=r"[A-Za-z0-9][A-Za-z0-9 .,!?'&:-]*",
    ),
    "description": FieldRule(500, multiline=True),
    "hero_description": FieldRule(120),
    "answer": FieldRule(80),
    "style_tag": FieldRule(
        24, ascii_only=True, pattern=r"[a-z][a-z_]{1,23}", hint="Style tags are lowercase words."
    ),
}


def _to_ascii(text: str) -> str:
    text = text.translate(_ASCII_PUNCT)
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if ch.isascii())


def clean_text(
    text: str, *, max_len: int, multiline: bool = False, ascii_only: bool = False
) -> str:
    """Return a cleaned copy of ``text``. Never raises for content, only for wrong types."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    text = text[: max_len * 4 + 64]  # bound the work before normalising
    text = unicodedata.normalize("NFKC", text).replace("\r\n", "\n").replace("\r", "\n")
    out: list[str] = []
    marks = 0
    for ch in text:
        if ch == "\n":
            out.append("\n" if multiline else " ")
            marks = 0
            continue
        if ch == "\t":
            out.append(" ")
            continue
        cat = unicodedata.category(ch)
        if cat in _DROP_CATEGORIES:
            continue
        if cat.startswith("M"):
            marks += 1
            if marks > _MAX_MARKS:
                continue
        else:
            marks = 0
        if cat in ("Zl", "Zp", "Zs"):
            ch = "\n" if (multiline and cat != "Zs") else " "
        out.append(ch)
    text = "".join(out)
    if ascii_only:
        text = _to_ascii(text)
    lines = [_SPACES.sub(" ", line).strip() for line in text.split("\n")]
    text = _MANY_NEWLINES.sub("\n\n", "\n".join(lines)).strip()
    return text[:max_len].rstrip()


def sanitize(field: str, text: str) -> str:
    """Clean ``text`` for a known wizard field and enforce its allowlist.

    Raises ``InputRejected`` (with a plain-English ``message``) if it can't be used.
    """
    rule = FIELDS.get(field)
    if rule is None:
        raise KeyError(f"unknown field {field!r}; add it to FIELDS")
    if not isinstance(text, str):
        raise InputRejected(field, "Please type some text.")
    cleaned = clean_text(
        text, max_len=rule.max_len, multiline=rule.multiline, ascii_only=rule.ascii_only
    )
    if len(cleaned) < rule.min_len:
        raise InputRejected(field, "Please type at least one letter or number.")
    if rule.pattern and cleaned and not re.fullmatch(rule.pattern, cleaned):
        raise InputRejected(field, rule.hint or "Some characters can't be used here.")
    return cleaned


def clean_choice(value: object, allowed: set[str] | frozenset[str] | list[str]) -> str:
    """Drop-down values must be one of the offered options, exactly."""
    if not isinstance(value, str) or value not in allowed:
        raise InputRejected("choice", "Please pick one of the options in the list.")
    return value


_RESERVED = {"con", "prn", "aux", "nul", "conin$", "conout$"} | {
    f"{p}{n}" for p in ("com", "lpt") for n in "0123456789\u00b9\u00b2\u00b3"
}


def safe_filename(name: str, ext: str = "", *, fallback: str = "my-game") -> str:
    """Make a file name that is safe on Windows and Linux (no paths, no reserved names)."""
    base = clean_text(name if isinstance(name, str) else "", max_len=120, ascii_only=True)
    base = re.sub(r"[^A-Za-z0-9 _-]+", "", base)
    base = re.sub(r"[ _]+", "_", base).strip("._- ")[:64].rstrip("._- ")
    if not base or base.split(".")[0].lower() in _RESERVED:
        base = fallback
    ext = re.sub(r"[^a-z0-9]", "", ext.lower())[:8]
    return f"{base}.{ext}" if ext else base


def safe_join(base: str | Path, *parts: str) -> Path:
    """Join ``parts`` under ``base`` and refuse anything that escapes it (../, absolute, links)."""
    root = Path(base).resolve()
    target = root.joinpath(*parts).resolve()
    if target != root and root not in target.parents:
        from .errors import SandboxError

        raise SandboxError(f"path escapes {root}: {'/'.join(parts)!r}")
    return target
