"""Prompt-text guarding (kept for the prompt templates in ai/prompts.py).

RetroBake makes covers and names offline and sends no prompts anywhere; these checks stay
so any future template keeps user text quoted, scrubbed and bounded.

Rules for the ai-art prompt builder:
1. Prompts come from a FIXED template in code. User text only fills marked slots.
2. Every slot value goes through ``quote_user_text`` (sanitize + IP scrub + strip
   instruction-like text + wrap in quotes).
3. The finished prompt goes through ``check_prompt`` before it is used.
4. Any generated text goes through outputs.validate_name / validate_image.
"""

from __future__ import annotations

import re

from .errors import InputRejected
from .ipguard import NEUTRAL, find_ip, scrub_ip
from .sanitizer import clean_text

MAX_PROMPT_CHARS = 900

# Phrases that try to steer the AI instead of describing the game. No leading word
# boundaries: a letter glued in front ("Xignore ...", any script, digits, "_") must not hide them.
_INJECTION = re.compile(
    r"(?is)(?:ignore|disregard|forget|override|overrule|bypass|skip)"
    r"[^.\n]{0,40}?(?:instruction|prompt|rule|above|previous|prior|system|guideline)s?"
    r"|(?:system|assistant|developer|user|human|ai)\s*(?:prompt|message|role)?\s*[:>]"
    r"|you\s+are\s+now|new\s+instructions?|jailbreak|dan\s+mode|developer\s+mode"
    r"|act\s+as|pretend\s+(?:to\s+be|you)|nsfw|nude|naked|gore"
)
_URL = re.compile(r"(?i)\b(?:https?://|www\.)\S+|\b\S+\.(?:com|net|org|io|ai|xyz|ru|cn)\b")
_META = re.compile(r"[<>{}\[\]`|\\^~\"#*=]+")


def quote_user_text(text: str, *, max_len: int = 200) -> str:
    """Make user text safe to drop into a prompt slot. Returns a double-quoted string."""
    cleaned = clean_text(text, max_len=max_len)
    for _ in range(8):  # removing one phrase can join the pieces of another
        before = cleaned
        cleaned = _URL.sub(" ", cleaned)
        cleaned = _INJECTION.sub(" ", cleaned)
        cleaned = _META.sub(" ", cleaned)
        if cleaned == before:
            break
    else:
        cleaned = ""
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
    if _INJECTION.search(prompt):
        raise InputRejected("prompt", "The art request had instructions in it, so it was stopped.")
    if find_ip(prompt) or _URL.search(prompt):
        raise InputRejected("prompt", "The art request mentioned another game, so it was stopped.")
    return prompt.strip()


__all__ = [
    "MAX_PROMPT_CHARS",
    "NEUTRAL",
    "check_prompt",
    "quote_user_text",
]
