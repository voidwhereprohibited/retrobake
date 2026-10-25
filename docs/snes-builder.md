# SNES builder (contract `snes-builder`, owner: snes-engine)

Same shape as `nes-builder`, so the wizard can bake either system with the same calls.

```python
from retrobake.builders import snes

result = snes.bake(spec)            # spec = validated game-spec dict, system "snes"
rom_bytes = result.rom             # complete headerless LoROM image, save it as .sfc
```

## API
- `bake(spec, *, wla_dir=None, limits=None) -> SnesRom`
  - `SnesRom(rom: bytes, title: str, engine: str, mapper: str, network_isolated: bool)`
  - Runs `retrobake.spec.validate`, then `security.sanitize("title")` + `check_title`, picks the
    engine, builds the data files, then wla-65816 + wlalink through `security.run_build` in a
    `BuildWorkspace`, then patches the internal header name (title in plain uppercase ASCII) and
    rewrites the checksum. Deterministic: the same spec always gives byte-identical ROMs.
- `SnesBuildError(message, detail)` - the only error `bake` raises. `message` is plain English
  for the UI; `detail` is tool output for logs/bug reports.
- `engine_for(spec)` - `"platformer"` for side-view specs (`movement: side_jump`), else `"hello"`
  (title-screen placeholder until the top-down engine lands, M3).
- `find_wladx(wla_dir=None) -> Path` - toolchain folder. Search order: argument,
  `RETROBAKE_WLA_DIR`, `<app>/toolchains/pvsneslib/bin`,
  `<app>/toolchains/pvsneslib/<linux|windows>/bin` (`<app>` = PyInstaller `_MEIPASS` when
  frozen, else the repo root).
- `templates_dir()` = `<app>/templates/snes`. `check_rom(rom, size=None)` checks size, LoROM map
  byte, checksum/complement and reset vector. `checksum(rom)`, `header_name(title)`.
- Data builders (pure, tested): `config_data(spec)`, `level_data(spec)`, `text_data(title, engine)`,
  `data_files(spec, title, engine)`.
- Constants: `ROM_SIZES` (`platformer` 128 KB, `hello` 32 KB), `MAPPER` ("LoROM"), `ENGINE`,
  `HEADER` ($7FC0), `COMBAT_IDS`, `EXTRA_FLAGS`.

## Platformer engine (M2) - `templates/snes/platformer/`
128 KB LoROM, SlowROM, NTSC, no SRAM. Bank 0 engine + text/config, bank 1 the level pack,
bank 2 sprites/HUD art, bank 3 the 12 setting tile sets.

- **Video:** mode 1. BG1 = level (16x16 tiles, 4bpp, streamed one column per frame as the camera
  scrolls, 16 screens max), BG2 = parallax backdrop at half speed (4 hill styles), BG3 = HUD and
  messages (8x8 2bpp, high priority). HDMA paints a sky gradient into colour 0. Sprites 16x16,
  boss 32x32.
- **Hero:** run (Y/X held in stomp or no-fight games), variable-height jump with coyote time and
  jump buffering. Jump = about 61 px (3.8 tiles) high and 85 px (5.3 tiles) long at walking speed,
  above the level-data floor of 3 x 5 tiles. Hitbox 10 x 14 px.
- **Level data:** decodes the `RBLV` pack from `retrobake.spec.platformer` (contract `level-data`)
  in 65816: column RLE -> a 256 x 16 map in WRAM $7E:2000. Tiles: ground/fill/block solid,
  one-way platforms, spikes hurt, doors are solid until the key is picked up (then every door
  opens and the screen redraws).
- **Objects:** up to 96 per level, 10 active at once, spawned as they come into view and parked
  again when they leave. walker (turns at walls and ledges), hopper (hops toward the hero),
  flyer (sine wave), boss (3 hits, hops; the goal flag stays grey until it is beaten), gem
  (coin), heart, extra life, key, shop sign (Up: 10 gems -> a heart, or a life).
- **Combat** (spec `modules.combat`): `stomp` jump on enemies; `melee` Y/X swings a sword;
  `projectile` Y/X shoots (2 shots on screen); `none` enemies can't be hurt (spec rules leave
  bosses out of no-fight games).
- **Extras** (spec `modules.extras`): `hearts` 3 hearts (up to 5), `lives` 3 lives + game over,
  `collectibles` gems (100 = extra life), `score` 6-digit score, `timer` level time limit,
  `shop`, `keys_doors`, `bosses` come from the level pack.
- **Flow:** title (signature state 1) -> Start -> "STAGE n" -> play (Start pauses) -> goal flag ->
  "STAGE CLEAR!" -> next stage ... -> "YOU WIN!" -> title. Falling in a pit, running out of
  hearts or time costs a life and restarts the stage; no lives left -> "GAME OVER" -> title.
- **Art:** all original (`builders/snes_gfx.py`): 8 hero archetypes (knight, explorer, robot,
  animal, wizard, kid, ninja, pilot), 3 enemies, a boss, items, 12 settings x 8 terrain tiles,
  backdrops; spec `style.palette_mood` recolours terrain, backdrop and enemies.
- **Not yet:** music/sound (SPC700) - a later task.

### Data files (the only thing the builder writes)
| File | Size | Content |
|---|---|---|
| `text.bin` | var | title screen lines `[len, off_lo, off_hi, tile...]...0` (BG3 cell offsets) |
| `config.bin` | 16 | combat id, extras flags, start lives (BCD), start hearts |
| `ascii.bin` | 128 | ASCII -> font tile, for the engine's own fixed messages |
| `levels.bin` | <= 32 KB | `RBLV` level pack (contract `level-data`) |
| `objtiles.bin` / `objpal.bin` | 8192 / 256 | sprite sheet (hero archetype) / 8 sprite palettes |
| `hudtiles.bin` / `hudpal.bin` | var / 64 | font + HUD icons (2bpp) / BG3 palettes |
| `bg2map.bin` | 8192 | 4 backdrop maps |
| `settings.bin` | 30720 | 12 x 2560: tiles, terrain + backdrop palettes, sky HDMA, backdrop variant |

### Debug probe (for tests; WRAM, libretro SYSTEM_RAM offsets)
Written every frame of play and on the title screen, next to qa's boot signature:

| Offset | Size | Value |
|---|---|---|
| $1FF0 | 2 | hero x, pixels |
| $1FF2 | 2 | hero y, pixels (signed; level row 0 = 0) |
| $1FF4 | 1 | stage index (0-based) |
| $1FF5 | 1 | game state: 0 title, 1 stage intro, 2 play, 3 dying, 4 stage clear, 5 game over, 6 win |
| $1FF6 | 1 | lives (BCD) |
| $1FF7 | 1 | hearts |
| $1FF8 | 1 | gems (BCD) |
| $1FF9 | 1 | bit0 on ground, bit1 key held or boss beaten |
| $1FFA | 2 | frame counter (one tick per engine frame) |
| $1FFC | 4 | qa boot signature "RB" 1 state |

## M1 "hello" engine - `templates/snes/hello/`
32 KB LoROM title screen (title, "PRESS START", credit) used for movement types without an SNES
engine yet; Start sets signature state 2 and turns the backdrop green.

## Safety
- Templates (`main.asm`, `linkfile`) are fixed code. The builder writes only binary data files
  the template `.INCBIN`s, so user text is never parsed as assembly; it reaches the ROM only as
  font tile numbers in `text.bin` and as the plain-ASCII header name patched in after linking.
  `config.bin` comes only from spec enums. Tool argv is constant.

## Tests
- `tests/builders/test_snes.py` - data files, config mapping, level pack, real bakes (CI).
- `tools/snes_play_test.py` - CI: bakes 4 sample games (every combat style, every extra), boots
  each on the Snes9x libretro core, checks signature, Start, Right moves, B jumps, then 1500
  frames of scripted play (no fatal state, game loop keeps pace), saves a PNG screenshot.
- qa's `tests/emulator/run_smoke.py` boots `tools/bake_sample_snes.py` output (platformer +
  top-down placeholder).

## Toolchain
`tools/build_snes_toolchain.sh` builds wla-65816 + wlalink only, from the exact WLA-DX commit
PVSnesLib 4.6.0 pins (`compiler/wla-dx` = 6fa1f673), native Linux + static mingw-w64 Windows
`.exe`, into `toolchains/pvsneslib/{linux,windows}/bin` with WLA-DX's `LICENSE`
(GPL-2.0-or-later). CI job `snes-toolchain` builds/caches it; `snes-bake` runs the builder tests,
bakes the samples, boots them with qa's smoke test and runs the play test, on Ubuntu and Windows.
Release bundles the matching folder as `toolchains/pvsneslib/bin` plus `templates/snes/`.
