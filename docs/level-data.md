# level-data contract (v1)

Owner: **game-design**. Used by nes-engine and snes-engine (M2 platformer). Don't change it without a `note` to game-design and a new `decide` entry.

- Generator: `retrobake.spec.platformer.generate_levels(spec) -> LevelPack`
- Data model, binary format, reference decoder, playability checker: `retrobake.spec.levels`
- Errors: `UnsupportedSpec(.message plain English)` for invalid specs or top-down movement (M3)

```python
from retrobake.spec.platformer import generate_levels
pack = generate_levels(spec)      # deterministic: same spec + seed -> same bytes
blob = pack.encode()              # "RBLV" pack, fits BUDGETS[system]; .incbin it as data
for level in pack.levels: ...     # or use Level objects directly
```

## What gets generated

| Spec | Levels |
|---|---|
| `side_jump` + `linear_levels` | `world.levels` stages, longer as you go (3 screens up to the system max) |
| `side_jump` + `dungeons_items` | `world.dungeons` stages, each with a key and a locked door |
| `side_jump` + `open_map` | 1 long stage: small 6 / medium 10 / large 16 screens (capped per system) |
| `topdown_walk` | not yet (M3): `UnsupportedSpec` |

Extras: `collectibles` → coins (on platforms, over gaps, in lines); `hearts` → 1 heart per stage; `lives` → 1 extra life every 2nd stage (on a high platform when there is one); `keys_doors` → key + door wall in the end zone; `bosses` → boss arena (last screen) on the last stage and every 4th stage; `shop` → shop sign at the start of stages 2+; `timer` → `time_limit` seconds; `score` → HUD only (nothing in the level). Combat `none` → walkers only, half as many.

Every level passes `check_playable()` before it's returned: the goal is reachable from the start, the key is reachable, and the goal is **not** reachable without the key.

## Grid

- Metatiles are 16×16 px. `HEIGHT = 12` rows (192 px), `width` = screens × 16 columns. Max screens: NES 8, SNES 16 (≤ 256 columns, so x fits a byte).
- Origin top-left, `x` = column, `y` = row. A standing object at `(x, y)` stands on tile `(x, y+1)`.
- Rows 12+ on screen are yours for the HUD (NES has 15 rows, SNES 14).
- Columns that are all `empty` are bottomless pits: falling below row 11 loses a life/heart.

| Id | Tile | Rule |
|---|---|---|
| 0 | empty | air |
| 1 | ground | solid, ground surface |
| 2 | fill | solid, earth below the surface |
| 3 | block | solid block / pillar / wall above a door |
| 4 | platform | one-way: land on top, jump up through it from below |
| 5 | spikes | solid, hurts on touch |
| 6 | door | solid until the hero has the key, then open (non-solid) |
| 7 | decor | background only, not solid (unused in v1; reserved for engines' scenery) |

## Objects

| Id | Kind | Notes |
|---|---|---|
| 1 | walker | walks on the ground, turns at walls and ledges |
| 2 | hopper | hops in place / toward the hero |
| 3 | flyer | floats in a slow wave around its start (placed 3 rows above ground) |
| 4 | coin | collectible |
| 5 | heart | restores one heart / hit |
| 6 | life | extra life |
| 7 | key | opens the level's door |
| 8 | boss | 2×2 metatiles, `(x, y)` = bottom-left; the goal only works once it's beaten |
| 9 | shop | shop sign: spend coins |

Never more than 3 enemies per screen; objects per level ≤ NES 40 / SNES 96 (coins dropped first).

## Physics floor (engines must meet this)

The generator never needs more than `JUMP = {"rise": 2, "reach": 4}`: climb at most 2 tiles, land at most 4 columns away at the same or lower height (3 columns when going up 1 tile, 2 when going up 2), with 2 tiles of headroom at the top of the jump. Give the hero **at least a 3-tile-high, 5-tile-long jump** so every level has margin.

## Binary format

**Pack** (`LevelPack.encode()`), all little-endian:

| Bytes | Field |
|---|---|
| 0–3 | `"RBLV"` |
| 4 | format version (1) |
| 5 | system: 0 NES, 1 SNES |
| 6 | level count N |
| 7… | N × u16 offset of each level record from the start of the pack |

Budgets for the whole pack: NES 6144 bytes, SNES 32768 bytes (the generator shortens levels if needed). Typical: 3 NES stages ≈ 0.7 KB, 16 SNES stages ≈ 6 KB.

**Level record** (`Level.encode()`):

| Byte | Field |
|---|---|
| 0 | screens (1–16); width = screens × 16 |
| 1 | flags: bit0 boss, bit1 key_door |
| 2–3 | time limit, seconds (u16, 0 = none) |
| 4, 5 | start x, y |
| 6, 7 | goal x, y |
| 8 | setting id = index in `catalog()["settings"]` (0 grassland … 11 sky) |
| 9 | object count M |
| 10… | M × 3 bytes `kind, x, y`, sorted by x (stream them in as the camera scrolls) |
| then | column records, left to right, until `width` columns are filled |

**Column record:** one header byte `(repeat - 1) << 4 | runs`, then `runs` bytes of `tile << 4 | (length - 1)`, top to bottom (lengths add up to 12). The column repeats `repeat` (1–16) times. Reference decoder: `levels.decode_level()` (≈ 20 lines; port it to 6502 / 65816).

## JSON (debugging, tests)

`LevelPack.to_dict()` gives the same data with each row as a hex string (`"0001112222…"`, one character per tile) and named objects.
