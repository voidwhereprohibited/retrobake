"""Offline, deterministic, original-only cover art and name ideas (no network, stdlib only).

Same spec + seed + variant always gives the same picture and names, on Windows and Linux.
"""

from __future__ import annotations

import math
import random
import zlib
from typing import Any

from retrobake.security import InputRejected, check_title, sanitize

from .raster import Canvas, Color

PIXEL = 8  # one "retro pixel" = 8x8 real pixels
COVER_SIZE = {"nes": (512, 704), "snes": (704, 512)}  # portrait NES box, landscape SNES box

# setting -> sky top, sky bottom, ground, ground shade, feature colour, feature kind
_SETTINGS: dict[str, tuple[Color, Color, Color, Color, Color, str]] = {
    "grassland": (
        (92, 148, 252),
        (188, 224, 255),
        (56, 160, 64),
        (24, 104, 40),
        (36, 124, 52),
        "hills",
    ),
    "forest": ((60, 110, 170), (170, 210, 190), (40, 110, 50), (20, 70, 30), (16, 80, 40), "trees"),
    "castle": (
        (40, 40, 110),
        (150, 110, 170),
        (110, 100, 100),
        (70, 60, 70),
        (60, 50, 80),
        "towers",
    ),
    "cave": ((20, 16, 30), (70, 50, 60), (90, 70, 50), (50, 36, 28), (60, 44, 40), "stalactites"),
    "desert": (
        (250, 170, 90),
        (255, 230, 160),
        (230, 190, 110),
        (190, 140, 70),
        (210, 150, 80),
        "dunes",
    ),
    "ocean": (
        (60, 140, 230),
        (170, 220, 250),
        (30, 90, 190),
        (20, 60, 140),
        (240, 250, 255),
        "waves",
    ),
    "ice": (
        (120, 170, 230),
        (220, 240, 255),
        (230, 245, 255),
        (160, 200, 230),
        (190, 220, 245),
        "peaks",
    ),
    "volcano": ((60, 20, 30), (220, 90, 40), (70, 40, 40), (40, 20, 20), (90, 40, 40), "volcano"),
    "city": ((30, 30, 80), (230, 120, 120), (60, 60, 70), (30, 30, 40), (40, 40, 70), "skyline"),
    "space": ((5, 5, 25), (40, 20, 80), (90, 90, 110), (50, 50, 70), (200, 120, 60), "stars"),
    "haunted": ((20, 20, 40), (90, 60, 120), (50, 60, 50), (30, 36, 30), (40, 40, 60), "graves"),
    "sky": (
        (90, 160, 255),
        (255, 220, 200),
        (250, 250, 255),
        (220, 230, 250),
        (255, 255, 255),
        "clouds",
    ),
}
# palette mood -> hero main, hero second, accent
_MOODS: dict[str, tuple[Color, Color, Color]] = {
    "bright": ((228, 48, 40), (252, 200, 140), (252, 216, 40)),
    "pastel": ((240, 140, 180), (255, 225, 205), (170, 220, 250)),
    "warm": ((216, 88, 24), (252, 200, 140), (252, 180, 60)),
    "earthy": ((136, 96, 48), (230, 190, 140), (170, 150, 60)),
    "icy": ((60, 120, 220), (230, 240, 255), (150, 230, 255)),
    "neon": ((255, 40, 200), (40, 255, 220), (250, 250, 60)),
    "dark": ((120, 40, 160), (200, 180, 200), (200, 60, 60)),
    "spooky": ((120, 200, 80), (220, 220, 200), (250, 140, 30)),
}
_TINT: dict[str, tuple[Color, float, float]] = {  # tint colour, strength, brightness
    "bright": ((255, 255, 255), 0.0, 1.05),
    "pastel": ((255, 240, 250), 0.35, 1.0),
    "warm": ((255, 150, 60), 0.18, 1.0),
    "earthy": ((140, 100, 60), 0.25, 0.95),
    "icy": ((190, 225, 255), 0.30, 1.0),
    "neon": ((60, 0, 90), 0.30, 0.9),
    "dark": ((10, 10, 30), 0.25, 0.6),
    "spooky": ((60, 20, 90), 0.30, 0.7),
}
_SPRITES = {  # half sprites (mirrored): X body, H second colour, E eye
    "human": [
        "...HH",
        "..HHH",
        "..HEH",
        "..HHH",
        "...XX",
        ".XXXX",
        "X.XXX",
        "X.XXX",
        "..XXX",
        "..X.X",
        "..X..",
        ".XX..",
    ],
    "robot": [
        "....X",
        "..XXX",
        "..XEX",
        "..XXX",
        "...XX",
        ".XXXX",
        "XXXXX",
        "X.XXX",
        "..XXX",
        "..X.X",
        "..X..",
        ".XX..",
    ],
    "animal": [
        ".H...",
        ".HH..",
        ".HHHH",
        ".HEHH",
        "..HHH",
        "..XXX",
        ".XXXX",
        ".XXXX",
        ".XXXX",
        "..X.X",
        "..X.X",
        ".XX.X",
    ],
    "ship": [
        "....X",
        "...XX",
        "...XX",
        "..XEX",
        "..XXX",
        ".XXXX",
        "XXXXX",
        "XXXXX",
        "X.XXX",
        "..X.X",
        "..H.H",
        "...H.",
    ],
}
_BAYER = ((0, 8, 2, 10), (12, 4, 14, 6), (3, 11, 1, 9), (15, 7, 13, 5))


def _rng(spec: dict[str, Any], variant: int, salt: str) -> random.Random:
    raw = spec.get("seed") if isinstance(spec, dict) else 0
    seed = (raw if isinstance(raw, int) and not isinstance(raw, bool) else 0) & 0xFFFFFFFF
    # Deterministic art/names, not security: same spec must give the same cover everywhere.
    return random.Random(zlib.crc32(f"{salt}:{seed}:{variant}".encode()))  # noqa: S311


def _mix(a: Color, b: Color, t: float) -> Color:
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))  # type: ignore[return-value]


def _tint(c: Color, mood: str) -> Color:
    tc, strength, bright = _TINT.get(mood, _TINT["bright"])
    m = _mix(c, tc, strength)
    return tuple(max(0, min(255, int(v * bright))) for v in m)  # type: ignore[return-value]


def _dark(c: Color, f: float = 0.45) -> Color:
    return tuple(int(v * f) for v in c)  # type: ignore[return-value]


def _pick(spec: dict[str, Any], *path: str, default: str) -> str:
    node: Any = spec
    for key in path:
        node = node.get(key) if isinstance(node, dict) else None
    return node if isinstance(node, str) else default


def _sky(c: Canvas, top: Color, bottom: Color, horizon: int) -> None:
    steps = [_mix(top, bottom, i / 4) for i in range(5)]
    for y in range(horizon):
        t = 4 * y / max(1, horizon - 1)
        base = min(3, int(t))
        frac = t - base
        for x in range(c.width):
            pick = base + 1 if frac * 16 > _BAYER[y % 4][x % 4] else base
            c.set(x, y, steps[pick])


def _disc(c: Canvas, cx: int, cy: int, r: int, color: Color) -> None:
    for y in range(cy - r, cy + r + 1):
        for x in range(cx - r, cx + r + 1):
            if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                c.set(x, y, color)


def _features(c: Canvas, kind: str, color: Color, horizon: int, rng: random.Random) -> None:
    w, h = c.width, c.height
    if kind in ("hills", "dunes"):
        phase = rng.randint(0, 60)
        for x0 in range(w):
            x = x0 + phase
            for k, (amp, per) in enumerate(((5, 23), (3, 11))):
                top = horizon - int(amp + amp * math.sin((x + k * 7) / per * 6.28))
                c.fill_rect(x0, top, 1, horizon - top, _dark(color, 1 - 0.15 * k))
    elif kind == "trees":
        x = -2
        while x < w:
            th = rng.randint(7, 14)
            for i in range(th):
                half = (i * 4) // th
                c.fill_rect(x + 3 - half, horizon - th + i, 2 * half + 1, 1, color)
            x += rng.randint(4, 7)
    elif kind in ("towers", "skyline", "graves"):
        x = rng.randint(0, 4)
        while x < w:
            if kind == "graves":
                bw, bh = 3, rng.randint(3, 5)
            else:
                bw, bh = rng.randint(4, 8), rng.randint(6, 20 if kind == "skyline" else 14)
            c.fill_rect(x, horizon - bh, bw, bh, color)
            if kind == "towers":
                for cx in range(x, x + bw, 2):
                    c.fill_rect(cx, horizon - bh - 1, 1, 1, color)
            if kind == "skyline":
                for wy in range(horizon - bh + 1, horizon - 1, 2):
                    for wx in range(x + 1, x + bw - 1, 2):
                        if rng.random() < 0.5:
                            c.set(wx, wy, (250, 230, 120))
            x += bw + rng.randint(1, 4 if kind != "graves" else 7)
    elif kind == "stalactites":
        for x in range(0, w, 3):
            ln = rng.randint(2, 9)
            for i in range(ln):
                c.fill_rect(x + i // 4, i, max(1, 3 - i // 3), 1, color)
    elif kind in ("peaks", "volcano"):
        count = 1 if kind == "volcano" else 3
        for n in range(count):
            px = (n + 1) * w // (count + 1) + rng.randint(-4, 4)
            ph = h // 3 + rng.randint(-3, 3)
            for i in range(ph):
                half = i // (1 if kind == "peaks" else 1) + (3 if kind == "volcano" else 0)
                col = (245, 250, 255) if kind == "peaks" and i < ph // 4 else color
                c.fill_rect(px - half, horizon - ph + i, 2 * half + 1, 1, col)
            if kind == "volcano":
                c.fill_rect(px - 3, horizon - ph - 1, 7, 2, (255, 120, 30))
    elif kind == "stars":
        for _ in range(w * h // 40):
            c.set(rng.randrange(w), rng.randrange(horizon), (255, 255, 230))
        _disc(c, w * 3 // 4, horizon // 2, max(4, w // 10), color)
    elif kind == "clouds":
        for _ in range(5):
            cx, cy = rng.randrange(w), rng.randint(horizon // 3, horizon - 4)
            for dx in (-3, 0, 3):
                _disc(c, cx + dx, cy - (dx == 0), 3, color)
    elif kind == "waves":
        pass  # drawn on the ground (the sea)


def _sprite(kind: str, rng: random.Random, colors: tuple[Color, Color, Color]) -> Canvas:
    rows = _SPRITES[kind]
    main, second, accent = colors
    sw, sh = 10, len(rows)
    out = Canvas(sw + 2, sh + 2, (255, 0, 255))
    mask = []
    for half in rows:
        full = half + half[::-1]
        mask.append(full)
    swap = {(x, y) for y in range(sh) for x in range(5) if rng.random() < 0.18}
    for y, row in enumerate(mask):
        for x, ch in enumerate(row):
            if ch == ".":
                continue
            hx = x if x < 5 else 9 - x
            col = {"X": main, "H": second, "E": (16, 16, 24)}[ch]
            if ch == "X" and (hx, y) in swap:
                col = accent
            out.set(x + 1, y + 1, col)
    outline = _dark(main, 0.25)
    for y in range(out.height):
        for x in range(out.width):
            if out.get(x, y) != (255, 0, 255):
                continue
            near = any(
                0 <= x + dx < out.width
                and 0 <= y + dy < out.height
                and out.get(x + dx, y + dy) not in ((255, 0, 255), outline)
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
            )
            if near:
                out.set(x, y, outline)
    return out


def _paste(dst: Canvas, src: Canvas, x: int, y: int, key: Color = (255, 0, 255)) -> None:
    for sy in range(src.height):
        for sx in range(src.width):
            col = src.get(sx, sy)
            if col != key:
                dst.set(x + sx, y + sy, col)


def offline_art(spec: dict[str, Any], *, variant: int = 0) -> Canvas:
    """Procedural pixel-art cover picture (no title) sized for the spec's system."""
    system = _pick(spec, "system", default="nes")
    width, height = COVER_SIZE.get(system, COVER_SIZE["nes"])
    setting = _pick(spec, "world", "setting", default="grassland")
    mood = _pick(spec, "style", "palette_mood", default="bright")
    archetype = _pick(spec, "hero", "archetype", default="explorer")
    genres = spec.get("genres") if isinstance(spec.get("genres"), list) else []
    rng = _rng(spec, variant, "cover")
    sky_t, sky_b, ground, shade, feat, kind = _SETTINGS.get(setting, _SETTINGS["grassland"])
    sky_t, sky_b, ground, shade, feat = (
        _tint(x, mood) for x in (sky_t, sky_b, ground, shade, feat)
    )
    hero_cols = _MOODS.get(mood, _MOODS["bright"])

    lw, lh = width // PIXEL, height // PIXEL
    c = Canvas(lw, lh)
    horizon = lh * 66 // 100
    _sky(c, sky_t, sky_b, horizon)
    if kind in ("hills", "trees", "peaks", "dunes", "clouds", "waves") and rng.random() < 0.7:
        _disc(c, lw // 5 + rng.randint(0, lw // 2), lh // 3, 3, _tint((255, 236, 140), mood))
    _features(c, kind, feat, horizon, rng)
    c.fill_rect(0, horizon, lw, lh - horizon, ground)
    for y in range(horizon, lh):
        for x in range(lw):
            if (x + y * 3) % 7 == 0 or (kind == "waves" and (x + 2 * (y - horizon)) % 9 < 2):
                c.set(x, y, feat if kind == "waves" else shade)
    c.fill_rect(0, horizon, lw, 1, _dark(ground, 0.7))

    # collectibles / extras by genre
    first = genres[0] if genres else "platformer"
    for _ in range(rng.randint(3, 6)):
        x, y = rng.randint(2, lw - 4), rng.randint(lh // 3, horizon - 6)
        if first == "puzzle":
            c.fill_rect(x, horizon - 2, 2, 2, hero_cols[rng.randrange(3)])
        elif first == "shooter":
            c.fill_rect(x, y, 3, 1, hero_cols[2])
            c.set(x + 1, y + 1, hero_cols[2])
        else:
            c.fill_rect(x, y, 1, 2, hero_cols[2])
    if first == "sports":
        _disc(c, lw * 2 // 3, horizon - 2, 1, (250, 250, 250))

    sprite_kind = {"robot": "robot", "animal": "animal"}.get(archetype, "human")
    if first == "shooter" or archetype == "pilot":
        sprite_kind = "ship"
    hero = _sprite(sprite_kind, rng, hero_cols).scaled(2)
    hx = (lw - hero.width) // 2
    hy = horizon - hero.height + 2 if sprite_kind != "ship" else horizon - hero.height - 6
    _paste(c, hero, hx, hy)

    big = c.scaled(PIXEL)
    frame = _dark(hero_cols[0], 0.35)
    for x, y, w, h in (
        (0, 0, width, 6),
        (0, height - 6, width, 6),
        (0, 0, 6, height),
        (width - 6, 0, 6, height),
    ):
        big.fill_rect(x, y, w, h, frame)
    return big


# ---------------------------------------------------------------- names
_S_WORDS = {
    "grassland": ["Meadow", "Clover", "Hilltop", "Sunny", "Green"],
    "forest": ["Wild", "Mossy", "Timber", "Thorn", "Hollow"],
    "castle": ["Royal", "Stone", "Crown", "Iron", "Banner"],
    "cave": ["Deep", "Crystal", "Echo", "Ember", "Gloom"],
    "desert": ["Sand", "Dune", "Mirage", "Sunbaked", "Dust"],
    "ocean": ["Tide", "Coral", "Wave", "Pearl", "Reef"],
    "ice": ["Frost", "Glacier", "Snow", "Polar", "Icicle"],
    "volcano": ["Magma", "Ember", "Ash", "Inferno", "Blaze"],
    "city": ["Neon", "Metro", "Rooftop", "Street", "Turbo"],
    "space": ["Cosmic", "Nova", "Orbit", "Comet", "Nebula"],
    "haunted": ["Phantom", "Grim", "Shadow", "Moonlit", "Spooky"],
    "sky": ["Cloud", "Aero", "Thunder", "Wind", "Skyhigh"],
}
_H_WORDS = {
    "knight": ["Knight", "Squire", "Paladin", "Shieldbearer"],
    "explorer": ["Explorer", "Ranger", "Trekker", "Scout"],
    "robot": ["Robo", "Bolt", "Circuit", "Gizmo"],
    "animal": ["Otter", "Badger", "Bunny", "Kitty"],
    "wizard": ["Wizard", "Mage", "Rune", "Spellcaster"],
    "kid": ["Kid", "Kiddo", "Rascal", "Buddy"],
    "ninja": ["Ninja", "Shuriken", "Blade", "Stealth"],
    "pilot": ["Pilot", "Ace", "Jet", "Wingman"],
}
_G_WORDS = {
    "platformer": ["Jump", "Dash", "Leap", "Run"],
    "topdown_adventure": ["Trail", "Journey", "Odyssey", "Expedition"],
    "rpg": ["Saga", "Chronicle", "Tales", "Legacy"],
    "shooter": ["Blaster", "Strike", "Assault", "Squadron"],
    "puzzle": ["Blocks", "Puzzle", "Tiles", "Match"],
    "sports": ["Cup", "League", "Slam", "Champions"],
}
_PLACES = {
    "grassland": "the Meadows",
    "forest": "the Wildwood",
    "castle": "Stonekeep",
    "cave": "the Deep",
    "desert": "the Dunes",
    "ocean": "the Tides",
    "ice": "Frostpeak",
    "volcano": "Mount Ember",
    "city": "Neon City",
    "space": "the Stars",
    "haunted": "Gloom Manor",
    "sky": "Cloudreach",
}
_PATTERNS = (
    "{S} {G}",
    "{H} {G}",
    "{G} of {P}",
    "{S} {H}",
    "{H}'s {G}",
    "Super {H} {G}",
    "{S} {G} II",
    "{S} {H} {G}",
    "{H} of {P}",
    "{G} {H}",
)


def _clean_name(name: str) -> str | None:
    try:
        return check_title(sanitize("name_idea", name), field="name_idea")
    except InputRejected:
        return None


def offline_names(spec: dict[str, Any], n: int = 6, *, variant: int = 0) -> list[str]:
    """Original name ideas built from the spec; always returns ``n`` names (n <= 12)."""
    n = max(1, min(12, n))
    rng = _rng(spec, variant, "names")
    setting = _pick(spec, "world", "setting", default="grassland")
    archetype = _pick(spec, "hero", "archetype", default="explorer")
    genres = [g for g in (spec.get("genres") or []) if isinstance(g, str)] or ["platformer"]
    s_words = _S_WORDS.get(setting, _S_WORDS["grassland"])
    h_words = _H_WORDS.get(archetype, _H_WORDS["explorer"])
    g_words = [w for g in genres for w in _G_WORDS.get(g, _G_WORDS["platformer"])]
    place = _PLACES.get(setting, "the Meadows")
    seen: set[str] = set()
    out: list[str] = []
    patterns = list(_PATTERNS)
    for attempt in range(400):
        if attempt % len(patterns) == 0:
            rng.shuffle(patterns)
        pat = patterns[attempt % len(patterns)]
        name = pat.format(
            S=rng.choice(s_words), H=rng.choice(h_words), G=rng.choice(g_words), P=place
        )
        clean = _clean_name(name)
        if clean and clean.casefold() not in seen:
            seen.add(clean.casefold())
            out.append(clean)
            if len(out) == n:
                break
    fallback = 1
    while len(out) < n:  # tiny word lists can't run dry the user's choice
        out.append(f"My Game {fallback}")
        fallback += 1
    return out
