"""AI prompt guarding for Pollinations (cover art + name ideas).

Rules for the ai-art prompt builder:
1. Prompts come from a FIXED template in code. User text only fills marked slots.
2. Every slot value goes through ``quote_user_text`` (sanitize + IP scrub + strip
   instruction-like text + wrap in quotes).
3. The finished prompt goes through ``check_prompt`` right before the request.
4. Requests always carry ``POLLINATIONS_REQUIRED_PARAMS`` (safe mode on, private,
   server-side prompt "enhance" off so their AI can't rewrite names back in).
5. Every response goes through outputs.validate_name / validate_image.
"""

from __future__ import annotations

import re

from .errors import InputRejected
from .ipguard import NEUTRAL, find_ip, scrub_ip
from .sanitizer import clean_text

POLLINATIONS_REQUIRED_PARAMS: dict[str, str] = {
    "safe": "true",
    "private": "true",
    "enhance": "false",
}
MAX_PROMPT_CHARS = 900

# Phrases that try to steer the AI instead of describing the game.
_INJECTION = re.compile(
    r"(?ix)\b(?:"
    r"ignore|disregard|forget|override|bypass)\b[^.\n]{0,40}?\b(?:"
    r"instruction|instructions|prompt|rules?|above|previous|prior|system)\b"
    r"|\b(?:system|assistant|developer|user)\s*(?:prompt|message|role)?\s*:"
    r"|\b(?:jailbreak|dan\s+mode|developer\s+mode|act\s+as|pretend\s+(?:to\s+be|you))\b"
    r"|\bnsfw\b|\bnude\b|\bnaked\b|\bgore\b"
)
_URL = re.compile(r"(?i)\b(?:https?://|www\.)\S+|\b\S+\.(?:com|net|org|io|ai|xyz|ru|cn)\b")
_META = re.compile(r"[<>{}\[\]`|\\^~\"#*=]+")


def quote_user_text(text: str, *, max_len: int = 200) -> str:
    """Make user text safe to drop into a prompt slot. Returns a double-quoted string."""
    cleaned = clean_text(text, max_len=max_len)
    cleaned = _URL.sub(" ", cleaned)
    cleaned = _INJECTION.sub(" ", cleaned)
    cleaned = _META.sub(" ", cleaned)
    cleaned, _ = scrub_ip(cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" .,;:-")
    return f'"{cleaned}"' if cleaned else '"an original game"'


def check_prompt(prompt: str) -> str:
    """Final gate before any AI request. Raises InputRejected if the prompt is unsafe."""
    if not isinstance(prompt, str) or not prompt.strip():
        raise InputRejected("prompt", "Something went wrong making the art request.")
    if len(prompt) > MAX_PROMPT_CHARS:
        raise InputRejected("prompt", "The game description is too long for the art request.")
    if clean_text(prompt, max_len=MAX_PROMPT_CHARS, multiline=True) != prompt.strip():
        raise InputRejected("prompt", "The art request had hidden characters and was stopped.")
    if find_ip(prompt) or _URL.search(prompt):
        raise InputRejected("prompt", "The art request mentioned another game, so it was stopped.")
    return prompt.strip()


__all__ = [
    "MAX_PROMPT_CHARS",
    "NEUTRAL",
    "POLLINATIONS_REQUIRED_PARAMS",
    "check_prompt",
    "quote_user_text",
]
