# game-spec contract (v1.0)

Owner: **game-design**. Every other agent builds on this. Don't change it without a `note` to game-design and a new `decide` entry.

- Schema: `src/retrobake/spec/game_spec.schema.json` (JSON Schema draft-07, validated with `fastjsonschema`)
- Catalog (labels, defaults, limits): `src/retrobake/spec/catalog.json`
- Python API: `retrobake.spec`

## Python API

| Call | Returns | Used by |
|---|---|---|
| `new_spec(system, genres, description="", title="My Game", seed=None)` | `(spec, fixes)` with every field filled | wizard-ui |
| `questions_for(spec)` | list of question dicts, in order | wizard-ui |
| `apply_answers(spec, {question_id: value})` | `(spec, fixes)` | wizard-ui |
| `resolve(spec)` | `(spec, fixes)` — conflict-free copy, input untouched | anyone |
| `validate(spec)` | list of error strings; `[]` = ready to bake (includes security's `check_title` + IP check on free text) | engines (must call before building), qa |
| `scrub_text(text)` | franchise-free text (style_refs then security `scrub_ip`) | wizard-ui |
| `style_from_text(text)` | `StyleHints(genres, modules, tags, palette_mood, clean_text, matched)` | security, ai-art |
| `catalog()`, `schema()`, `available_genres()` | data | wizard-ui (drop-down labels), ai-art |

`fixes` is a list of `Fix(rule, message)`; `message` is plain English for the wizard to show ("We adjusted a few things").

## Spec fields

| Field | Values |
|---|---|
| `spec_version` | `"1.0"` |
| `system` | `nes`, `snes` |
| `genres` | 1 or 2 of `platformer`, `topdown_adventure` (available now), `rpg`, `shooter`, `puzzle`, `sports` (planned). First = primary feel. |
| `title` | 1–24 chars, `A-Z a-z 0-9 space . , ! ? ' & : -`, starts with letter/digit |
| `description` | ≤ 500 chars, no control chars except tab/newline. Franchise names already replaced. |
| `hero.archetype` | `knight explorer robot animal wizard kid ninja pilot` |
| `hero.description` | optional, ≤ 120 chars, single line |
| `modules.movement` | `side_jump`, `topdown_walk`, `free_flight` (not built yet) |
| `modules.combat` | `stomp`, `melee`, `projectile`, `none` |
| `modules.progression` | `linear_levels`, `open_map`, `dungeons_items` |
| `modules.extras` | any of `hearts lives collectibles bosses keys_doors score timer shop` |
| `world.difficulty` | `easy normal hard` |
| `world.setting` | `grassland forest castle cave desert ocean ice volcano city space haunted sky` |
| `world.levels` | present only with `linear_levels` (NES 1–8, SNES 1–16) |
| `world.dungeons` | present only with `dungeons_items` (NES 1–4, SNES 1–8) |
| `world.map_size` | present only with `open_map` (`small medium` on NES, `+ large` on SNES) |
| `style.palette_mood` | `bright pastel warm earthy icy neon dark spooky` |
| `style.music_mood` | `heroic upbeat calm mysterious tense` |
| `style.tags` | generic tags from `STYLE_TAGS` only, never franchise names |
| `seed` | 0–4294967295; same spec + seed must bake the same ROM |

System limits: NES max 5 extras, 8 levels, 4 dungeons, medium map. SNES max 8 extras, 16 levels, 8 dungeons, large map.

## Genre modules

| Genre | Movement | Combat | Progression | Extras |
|---|---|---|---|---|
| platformer | side_jump | stomp | linear_levels | lives, collectibles, bosses |
| topdown_adventure | topdown_walk | melee | dungeons_items | hearts, keys_doors, bosses, collectibles |
| rpg (planned) | topdown_walk | melee | open_map | hearts, shop, collectibles, bosses |
| shooter (planned) | free_flight | projectile | linear_levels | lives, score, bosses |
| puzzle (planned) | topdown_walk | none | linear_levels | keys_doors, timer, score |
| sports (planned) | topdown_walk | none | linear_levels | score, timer |

## Mashups

The **primary** genre (first) decides how you move and fight; the **secondary** brings its world layout and extras. Hand-tuned recipes:

- `platformer + topdown_adventure` → side_jump, melee, dungeons_items, hearts/keys_doors/bosses/collectibles (side-scrolling dungeon adventure)
- `topdown_adventure + platformer` → topdown_walk, melee, linear_levels, lives/collectibles/bosses/score (top-down action stages)

Any other pair: primary movement + combat, secondary progression, extras from both; then `resolve()`.

The wizard asks "Which should it feel most like?" (`feel`) and "How should the world be laid out?" (`world_shape`) first for mashups.

## Incompatible combinations and how they're resolved

Every combination of modules goes through `resolve()`, so engines always receive a working set (tested over every combination on both systems).

| Rule | What happens |
|---|---|
| `stomp_needs_jump` | Stomp without side-view jumping → melee (top-down) or projectile (flying) |
| `flight_no_dungeons` | Free flight + dungeons → linear_levels |
| `flight_no_keys` | Free flight + keys_doors → keys_doors removed |
| `no_combat_no_bosses` | Combat `none` + bosses → bosses removed |
| `shop_needs_collectibles` | Shop without collectibles → collectibles added |
| `timer_only_in_stages` | Timer with open_map or dungeons_items → timer removed |
| `need_fail_state` | Combat but no hearts or lives → hearts (top-down) or lives added |
| `unavailable_module` | Module not built yet (free_flight) → closest available (side_jump) |
| `system_limits` | Too many extras/levels/dungeons or map too big → trimmed (extras kept by priority: hearts, lives, bosses, collectibles, keys_doors, score, shop, timer) |
| `world_fields` | Missing levels/dungeons/map_size for the layout → default (4 / 3 / medium) |

## Guided questions

Question dict: `id, prompt, help, kind (choice|multi|number|text), target, default, options[{value,label}], min, max, max_length, max_choices`.

Order: (mashup only) `feel`, `world_shape` → `hero_archetype`, `hero_description`, `setting`, `combat`, one of `levels` / `dungeons` / `map_size`, `extras`, `difficulty`, `palette_mood`, `music_mood`.

Options already exclude things that don't fit (no "Jump on enemies" in top-down, no timer outside stages, map sizes per system). Re-call `questions_for` after each answer. Every question has a default, so a "Skip" button always works.

## Franchise references

`style_from_text()` recognises names like "like Zelda meets Mario" (whole words, any case) and turns them into genres, module suggestions, generic style tags and a palette. `clean_text` has each name replaced with "a classic game". The franchise table lives only in `spec/style_refs.py` for recognition; nothing it outputs contains a franchise name. Security's IP guard is the final check before any text reaches AI or the ROM.

## Levels

Platformer level data comes from `retrobake.spec.platformer.generate_levels(spec)`; see `docs/level-data.md`.

## For engine agents

- Call `validate(spec)` first; refuse to build if it returns errors.
- Treat `title`, `description`, `hero.description` as data: escape for your data tables, never paste into assembly or shell.
- Use `seed` for all randomness.
- If a module isn't built in your engine yet, `note --to game-design` and we flip `available` in the catalog.
