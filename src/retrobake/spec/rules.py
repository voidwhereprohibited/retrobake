"""Module compatibility rules.

Any combination of modules the wizard can produce is passed through ``resolve()``, which turns
it into a combination that works on the chosen system and explains every change in plain
English (the wizard shows these as "We adjusted a few things" notes).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from .catalog import catalog, module_available, system_limits


@dataclass(frozen=True)
class Fix:
    rule: str
    message: str


# Documented incompatible combinations -> how they are resolved. Kept in sync with
# docs/game-spec.md by tests/spec/test_game_spec.py.
INCOMPATIBLE = {
    "stomp_needs_jump": "Stomp combat without side-view jumping -> melee (top-down) or "
    "projectile (flying).",
    "flight_no_dungeons": "Free flight + dungeons -> stages (linear_levels).",
    "flight_no_keys": "Free flight + keys/doors -> keys/doors removed.",
    "no_combat_no_bosses": "No combat + bosses -> bosses removed.",
    "shop_needs_collectibles": "Shop without collectibles -> collectibles added (money).",
    "timer_only_in_stages": "Time limit + open world or dungeons -> time limit removed.",
    "need_fail_state": "Combat with neither hearts nor lives -> hearts (top-down) or lives added.",
    "unavailable_module": "Module not built yet -> closest available module.",
    "system_limits": "Too many levels/dungeons/extras or map too big for the system -> trimmed.",
    "world_fields": "Missing levels/dungeons/map size for the chosen layout -> sensible default.",
}

_FALLBACK = {"free_flight": "side_jump"}


def _drop(extras: list[str], item: str) -> bool:
    if item in extras:
        extras.remove(item)
        return True
    return False


def resolve(spec: dict[str, Any]) -> tuple[dict[str, Any], list[Fix]]:
    """Return a fixed copy of ``spec`` plus the list of changes made. Never mutates the input."""
    spec = copy.deepcopy(spec)
    fixes: list[Fix] = []
    m = spec.setdefault("modules", {})
    world = spec.setdefault("world", {})
    extras: list[str] = list(dict.fromkeys(m.get("extras", [])))
    limits = system_limits(spec["system"])
    labels = catalog()["modules"]

    for kind in ("movement", "combat", "progression"):
        mod = m.get(kind)
        if mod and not module_available(kind, mod):
            new = _FALLBACK.get(mod, next(k for k, v in labels[kind].items() if v["available"]))
            m[kind] = new
            fixes.append(
                Fix(
                    "unavailable_module",
                    f'"{labels[kind][mod]["label"]}" isn\'t ready yet, so we used '
                    f'"{labels[kind][new]["label"]}" instead.',
                )
            )
    for item in [e for e in extras if not module_available("extras", e)]:
        extras.remove(item)
        fixes.append(
            Fix("unavailable_module", f"{labels['extras'][item]['label']} isn't ready yet.")
        )

    if m["combat"] == "stomp" and m["movement"] != "side_jump":
        m["combat"] = "melee" if m["movement"] == "topdown_walk" else "projectile"
        weapon = "a sword" if m["combat"] == "melee" else "a blaster"
        fixes.append(
            Fix(
                "stomp_needs_jump",
                f"Jumping on enemies needs a side view, so your hero gets {weapon}.",
            )
        )
    if m["movement"] == "free_flight" and m["progression"] == "dungeons_items":
        m["progression"] = "linear_levels"
        fixes.append(
            Fix("flight_no_dungeons", "Flying games play in stages, so dungeons became stages.")
        )
    if m["movement"] == "free_flight" and _drop(extras, "keys_doors"):
        fixes.append(
            Fix("flight_no_keys", "Keys and doors don't fit a flying game, so we left them out.")
        )
    if m["combat"] == "none" and _drop(extras, "bosses"):
        fixes.append(Fix("no_combat_no_bosses", "Bosses need a way to fight, so we left them out."))
    if "shop" in extras and "collectibles" not in extras:
        extras.append("collectibles")
        fixes.append(
            Fix("shop_needs_collectibles", "A shop needs money, so we added things to collect.")
        )
    if m["progression"] != "linear_levels" and _drop(extras, "timer"):
        fixes.append(
            Fix(
                "timer_only_in_stages",
                "A time limit only works in stage-by-stage games, so we left it out.",
            )
        )
    if m["combat"] != "none" and not {"hearts", "lives"} & set(extras):
        add = "hearts" if m["movement"] == "topdown_walk" else "lives"
        extras.insert(0, add)
        fixes.append(
            Fix("need_fail_state", f"Every action game needs a way to lose, so we added {add}.")
        )

    # System limits.
    if len(extras) > limits["max_extras"]:
        order = catalog()["extras_priority"]
        kept = sorted(extras, key=order.index)[: limits["max_extras"]]
        # protect dependencies after trimming
        if "shop" in kept and "collectibles" not in kept:
            kept.remove("shop")
        extras = [e for e in extras if e in kept]
        fixes.append(
            Fix(
                "system_limits",
                f"The {spec['system'].upper()} has room for {limits['max_extras']} extras, "
                "so we kept the most important ones.",
            )
        )

    prog = m["progression"]
    defaults = {"linear_levels": ("levels", 4), "dungeons_items": ("dungeons", 3)}
    if prog in defaults:
        key, default = defaults[prog]
        if key not in world:
            world[key] = default
            fixes.append(Fix("world_fields", f"We picked {default} {key} to start with."))
    if prog == "open_map" and "map_size" not in world:
        world["map_size"] = "medium"
        fixes.append(Fix("world_fields", "We picked a medium-size world to start with."))

    for key, cap in (("levels", limits["max_levels"]), ("dungeons", limits["max_dungeons"])):
        if world.get(key, 0) > cap:
            world[key] = cap
            fixes.append(
                Fix("system_limits", f"The {spec['system'].upper()} fits up to {cap} {key}.")
            )
    if world.get("map_size") and world["map_size"] not in limits["map_sizes"]:
        world["map_size"] = limits["map_sizes"][-1]
        fixes.append(
            Fix(
                "system_limits",
                f"The {spec['system'].upper()} fits up to a {world['map_size']} world.",
            )
        )
    # Drop world fields that don't apply to the chosen layout, so engines get a clean spec.
    for key, owner in (
        ("levels", "linear_levels"),
        ("dungeons", "dungeons_items"),
        ("map_size", "open_map"),
    ):
        if prog != owner:
            world.pop(key, None)

    m["extras"] = extras
    return spec, fixes


def problems(spec: dict[str, Any]) -> list[str]:
    """Semantic problems in an otherwise schema-valid spec (empty list = fine)."""
    out: list[str] = []
    for g in spec["genres"]:
        if not catalog()["genres"][g]["available"]:
            out.append(f"genre '{g}' is not available yet")
    _, fixes = resolve(spec)
    out.extend(f"{f.rule}: {f.message}" for f in fixes)
    return out
