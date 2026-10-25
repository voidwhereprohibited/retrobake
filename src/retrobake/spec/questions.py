"""Guided wizard questions, generated from the current (partial) spec.

The wizard calls ``questions_for(spec)`` and shows the questions in order. After each answer it
calls ``apply_answers(spec, {id: value})`` and then ``questions_for`` again, because options and
which questions appear depend on earlier answers (e.g. "How many dungeons?" only shows when the
world is laid out as dungeons). Every question has a default, so "Skip" always works.

Question dict format (also documented in docs/game-spec.md):
    id, prompt, help, kind ("choice" | "multi" | "number" | "text"), target (dotted spec path),
    default, options [{value, label}] for choice/multi, min/max for number, max_length for text.
"""

from __future__ import annotations

import copy
from typing import Any

from .catalog import catalog, genre_label, module_available, system_limits
from .rules import resolve


def _opts(mapping: dict[str, str]) -> list[dict[str, str]]:
    return [{"value": k, "label": v} for k, v in mapping.items()]


def _get(spec: dict[str, Any], path: str) -> Any:
    node: Any = spec
    for part in path.split("."):
        if isinstance(node, dict):
            node = node.get(part)
        elif isinstance(node, list) and part.isdigit() and int(part) < len(node):
            node = node[int(part)]
        else:
            return None
    return node


def questions_for(spec: dict[str, Any]) -> list[dict[str, Any]]:
    cat = catalog()
    mods = spec["modules"]
    limits = system_limits(spec["system"])
    labels = {
        k: {m: v["label"] for m, v in d.items() if v["available"]}
        for k, d in cat["modules"].items()
    }
    q: list[dict[str, Any]] = []

    def add(id_: str, prompt: str, kind: str, target: str, help_: str = "", **extra: Any) -> None:
        q.append(
            {
                "id": id_,
                "prompt": prompt,
                "help": help_,
                "kind": kind,
                "target": target,
                "default": _get(spec, target),
                **extra,
            }
        )

    genres = spec["genres"]
    if len(genres) == 2:
        add(
            "feel",
            "Which game type should it feel most like when you move around?",
            "choice",
            "genres.0",
            "The other one adds its world and extras.",
            options=[{"value": g, "label": genre_label(g)} for g in genres],
        )
        add(
            "world_shape",
            "How should the world be laid out?",
            "choice",
            "modules.progression",
            options=_opts(labels["progression"]),
        )

    add(
        "hero_archetype",
        "Who is your hero?",
        "choice",
        "hero.archetype",
        options=_opts(cat["hero_archetypes"]),
    )
    add(
        "hero_description",
        "Describe your hero in a few words (optional).",
        "text",
        "hero.description",
        "Example: a brave fox with a red scarf",
        max_length=120,
    )
    add(
        "setting",
        "Where does the adventure start?",
        "choice",
        "world.setting",
        options=_opts(cat["settings"]),
    )

    combat = dict(labels["combat"])
    if mods["movement"] != "side_jump":
        combat.pop("stomp", None)  # stomping needs jumping
    add(
        "combat",
        "How does your hero deal with enemies?",
        "choice",
        "modules.combat",
        options=_opts(combat),
    )

    prog = mods["progression"]
    if prog == "linear_levels":
        add(
            "levels",
            "How many stages?",
            "number",
            "world.levels",
            f"Up to {limits['max_levels']} on this system.",
            min=1,
            max=limits["max_levels"],
        )
    elif prog == "dungeons_items":
        add(
            "dungeons",
            "How many dungeons?",
            "number",
            "world.dungeons",
            f"Up to {limits['max_dungeons']} on this system.",
            min=1,
            max=limits["max_dungeons"],
        )
    else:
        add(
            "map_size",
            "How big is the world?",
            "choice",
            "world.map_size",
            options=[o for o in _opts(cat["map_sizes"]) if o["value"] in limits["map_sizes"]],
        )

    extras = dict(labels["extras"])
    if mods["combat"] == "none":
        extras.pop("bosses", None)
    if mods["movement"] == "free_flight":
        extras.pop("keys_doors", None)
    if prog != "linear_levels":
        extras.pop("timer", None)
    add(
        "extras",
        "Pick the extras you want.",
        "multi",
        "modules.extras",
        f"Pick up to {limits['max_extras']}.",
        options=_opts(extras),
        max_choices=limits["max_extras"],
    )

    add(
        "difficulty",
        "How hard should it be?",
        "choice",
        "world.difficulty",
        options=_opts(cat["difficulties"]),
    )
    add(
        "palette_mood",
        "What colors should it have?",
        "choice",
        "style.palette_mood",
        options=_opts(cat["palette_moods"]),
    )
    add(
        "music_mood",
        "What should the music feel like?",
        "choice",
        "style.music_mood",
        options=_opts(cat["music_moods"]),
    )
    return q


def apply_answers(spec: dict[str, Any], answers: dict[str, Any]) -> tuple[dict[str, Any], list]:
    """Apply wizard answers (question id -> value), then resolve conflicts.

    Unknown ids are ignored. Returns (new_spec, fixes) like ``rules.resolve``.
    """
    spec = copy.deepcopy(spec)
    by_id = {x["id"]: x for x in questions_for(spec)}
    for qid, value in answers.items():
        question = by_id.get(qid)
        if question is None:
            continue
        target = question["target"]
        if target == "genres.0":
            if value in spec["genres"] and value != spec["genres"][0]:
                from .builder import combine_modules  # local import avoids a cycle

                spec["genres"] = [value] + [g for g in spec["genres"] if g != value]
                spec["modules"] = combine_modules(spec["genres"])
            continue
        if target == "modules.progression" and not module_available("progression", value):
            continue
        section, key = target.split(".")
        if question["kind"] == "multi":
            allowed = {o["value"] for o in question["options"]}
            value = [v for v in value if v in allowed]
        spec.setdefault(section, {})[key] = value
    return resolve(spec)
