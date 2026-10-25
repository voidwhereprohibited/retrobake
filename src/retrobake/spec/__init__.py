"""RetroBake game-spec: the data model every other part of RetroBake builds on.

Public API (contract "game-spec", see docs/game-spec.md):
    new_spec(system, genres, description, title, seed) -> (spec, fixes)
    questions_for(spec) -> [question]
    apply_answers(spec, {question_id: value}) -> (spec, fixes)
    resolve(spec) -> (spec, fixes)
    validate(spec) -> [error]          # empty list = ready to bake
    style_from_text(text) -> StyleHints
    scrub_text(text) -> str             # franchise-free description/hero text
    platformer.generate_levels(spec) -> levels.LevelPack  # contract level-data
    catalog(), schema(), available_genres(), SPEC_VERSION
"""

from __future__ import annotations

from typing import Any

import fastjsonschema

from .builder import combine_modules, new_spec
from .catalog import SPEC_VERSION, available_genres, catalog, schema
from .questions import apply_answers, questions_for
from .rules import INCOMPATIBLE, Fix, problems, resolve
from .style_refs import STYLE_TAGS, StyleHints, style_from_text

_validator = None


def _ip_problems(spec: dict[str, Any]) -> list[str]:
    """Security's IP guard is the final gate: no franchise names in title or free text."""
    from retrobake.security import InputRejected, check_title, find_ip

    errors: list[str] = []
    try:
        check_title(spec["title"])
    except InputRejected as exc:
        errors.append(f"title: {exc.message}")
    for field, text in (
        ("description", spec.get("description", "")),
        ("hero.description", spec["hero"].get("description", "")),
    ):
        if text and find_ip(text):
            errors.append(f"{field}: contains a name from another game; use scrub_text() first")
    return errors


def scrub_text(text: str) -> str:
    """Franchise-free free text for description fields (style_refs pass, then security guard)."""
    from retrobake.security import scrub_ip

    return scrub_ip(style_from_text(text).clean_text)[0]


def validate(spec: Any) -> list[str]:
    """All reasons ``spec`` can't be baked. Empty list means it's valid and conflict-free."""
    global _validator
    if _validator is None:
        _validator = fastjsonschema.compile(schema())
    try:
        _validator(spec)
    except fastjsonschema.JsonSchemaValueException as exc:
        return [exc.message]
    errors = problems(spec)
    errors += _ip_problems(spec)
    errors += [
        f"unknown style tag '{t}'" for t in spec["style"].get("tags", []) if t not in STYLE_TAGS
    ]
    return errors


__all__ = [
    "INCOMPATIBLE",
    "SPEC_VERSION",
    "STYLE_TAGS",
    "Fix",
    "StyleHints",
    "apply_answers",
    "available_genres",
    "catalog",
    "combine_modules",
    "new_spec",
    "questions_for",
    "resolve",
    "schema",
    "scrub_text",
    "style_from_text",
    "validate",
]
