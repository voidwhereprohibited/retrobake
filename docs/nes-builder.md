# NES builder (contract `nes-builder`, owner: nes-engine)

```python
from retrobake.builders import nes

result = nes.bake(spec)  # spec = validated game-spec dict, system "nes"
rom_bytes = result.rom  # complete iNES file, write it with a .nes extension
```

## API
- `bake(spec, *, cc65_dir=None, limits=None) -> NesRom`
  - Side-view jumping specs (`modules.movement == "side_jump"`) go to the platformer engine
    below; anything else gets the "hello" engine (`bake_hello`, same arguments).
  - `NesRom(rom: bytes, title: str, engine: str, mapper: str, network_isolated: bool)`
  - Runs `retrobake.spec.validate`, then `security.sanitize("title")` + `check_title`, then
    ca65 + ld65 through `security.run_build` in a `BuildWorkspace`. Deterministic: the same
    spec always gives byte-identical ROMs.
- `NesBuildError(message, detail)` - the only error `bake` raises. `message` is plain English
  for the UI; `detail` is tool output for logs/bug reports (never show it as the main text).
- `find_cc65(cc65_dir=None) -> Path` - toolchain folder. Search order: argument,
  `RETROBAKE_CC65_DIR`, `<app>/toolchains/cc65/bin`, `<app>/toolchains/cc65/<linux|windows>/bin`
  (`<app>` = PyInstaller `_MEIPASS` when frozen, else the repo root).
- `templates_dir()` = `<app>/templates/nes`. `check_rom(rom)` sanity-checks an image.
- Constants: `ROM_BYTES` (24592 for NROM-128), `MAPPER`, `ENGINE`, `TITLE_ROW`, `CREDIT_ROW`.

## M1 output ("hello" engine)
NROM-128 (mapper 0, 16 KB PRG + 8 KB CHR, vertical mirroring). Title centred on row 12 and
"MADE WITH RETROBAKE" on row 22, white on black, RetroBake's own font
(`builders/nes_font.py`, charset = spec title charset, lowercase drawn as uppercase).
Implements qa's `rom-boot-signature`: `$07FC-$07FF` = `52 42 01 state` (1 title, 2 gameplay);
pressing Start switches to gameplay (backdrop turns dark blue). NMI drives a 1-frame main loop;
RAM for engine variables stops at `$07FB`. CI job `nes-bake` boots it on Mesen + FCEUmm.

## Safety
- The template (`templates/nes/hello/main.s`, `nrom.cfg`) is fixed code. The builder writes
  only binary data files (`text.bin` tile records, `font.chr`) that the template `.incbin`s,
  so user text is never parsed as assembly. Tool argv is constant.

## Toolchain
`tools/build_cc65.sh` builds ca65 + ld65 only (no C compiler/libraries: lighter) from a pinned
cc65 commit, native Linux + mingw-w64 Windows `.exe`, into `toolchains/cc65/{linux,windows}/bin`
with cc65's zlib `LICENSE`. CI job `cc65` builds/caches it and hands it to the test jobs;
release bundles the matching folder as `toolchains/cc65/bin` plus `templates/nes/`.

## Platformer engine (`builders/nes_platformer.py`, `templates/nes/platformer/`)
`nes_platformer.bake(spec)` turns a `side_jump` spec into a playable NROM-256 ROM (32K PRG,
8K CHR, 40976 bytes). `nes.bake` uses it for every `side_jump` spec.
- **Engine:** RetroBake's own ca65 assembly (`startup.s`, `game.s`). It calls the vendored
  nesdoug/neslib library (`third_party/nesdoug/LIB`, included unchanged) and plays music through
  FamiStudio's sound engine (`third_party/famistudio`). There is no C, so only ca65 and ld65 are
  needed; `startup.s` supplies the few cc65 runtime symbols neslib uses (`sp`, `popa`, `popax`).
- **Gameplay:** title screen, then Start. Walk with left/right and jump with A (3 tiles high,
  5 long). The camera scrolls smoothly, pixel by pixel: both nametables form a 512-pixel
  ring and each frame streams at most one missing metatile column through neslib's VRAM
  update buffer (two 24-tile vertical runs). Solid tiles and one-way platforms block; spikes,
  pits and enemies cost a life (three hearts, top left) and restart the level; with no lives
  left it goes back to the title. If there's a key, it opens doors. Reaching the goal flag
  goes to the next level; after the last level it goes back to the title.
- **Enemies:** up to 8 per level. Walkers (spec walkers and hoppers) walk slowly and turn at
  walls and ledges. Patrollers (spec flyers) pace 3 columns either side of where they start,
  ignoring ledges. In `stomp` combat games, landing on an enemy defeats it and bounces the
  hero; in other games enemies can only be avoided. Coins, hearts, extra lives, bosses and
  shops aren't drawn by this engine yet.
- **QA block:** `$07F0-$07F7` = lives, camera x (lo, hi), enemies alive, level, hero x (lo,
  hi), hero y. Emulator tests read it.
- **Data the builder writes** (the template `.incbin`s them; no user text becomes assembly):
  - `levels.bin` from `spec.platformer.generate_levels`, as described in `level_data`: a
    9-byte header (with a stomp flag), the enemy list, a column map and up to 42 unique
    nibble-packed columns per level.
  - `text.bin` title records.
  - `game.chr`: original placeholder art drawn in `nes_platformer_art.py`.
  - FamiStudio's NTSC note tables, computed and checked against upstream's SHA-256.
- **Music:** `music.s` is a short original placeholder tune in FamiStudio's data format.
- **Third-party code:** see `third_party/THIRD_PARTY_NOTICES` and `third_party/SHA256SUMS`.
  Release packaging must ship `third_party/` next to `templates/nes/`.
- **Tests:** `tests/builders/test_nes_platformer.py` checks the vendored hashes, the note
  tables, the level round-trip and the iNES header. It also boots the ROM in
  `tests/builders/cpu6502.py` (full official 6502 opcode set plus a small NES bus): title,
  Start, walk, jump, land, music writes, smooth scrolling with every column in view drawn,
  stomping (and getting hurt in avoid-only games), walker/patroller turning, lives, respawn
  and game over. `tests/emulator/test_platformer_emulator.py` plays the baked ROM in the
  FCEUmm libretro core through `tests/emulator/play_platformer.py` (skips without the core;
  set `RETROBAKE_FCEUMM_CORE`).
