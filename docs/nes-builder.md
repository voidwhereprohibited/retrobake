# NES builder (contract `nes-builder`, owner: nes-engine)

```python
from retrobake.builders import nes

result = nes.bake(spec)            # spec = validated game-spec dict, system "nes"
rom_bytes = result.rom             # complete iNES file, write it with a .nes extension
```

## API
- `bake(spec, *, cc65_dir=None, limits=None) -> NesRom(rom, title, engine, mapper, network_isolated)`.
  Deterministic: the same spec always gives byte-identical ROMs.
- `NesBuildError(message, detail)` - the only error. `message` is plain English for the UI;
  `detail` is tool output for logs/bug reports.
- `engine_for(spec)`: `"platformer"` for `movement == "side_jump"`, otherwise `"hello"`
  (title screen only, until the M3 top-down engine).
- `find_cc65(cc65_dir=None)`: argument > `RETROBAKE_CC65_DIR` > `<app>/toolchains/cc65/bin` >
  `<app>/toolchains/cc65/<linux|windows>/bin` (`<app>` = `sys._MEIPASS` when frozen, else repo root).
- `templates_dir()` = `<app>/templates/nes`; `check_rom(rom)`; `level_blob(spec, pack)`.
- Sizes: platformer `ROM_BYTES` = 40976 (NROM-256, mapper 0); hello `HELLO_ROM_BYTES` = 24592 (NROM-128).

## Platformer engine (M2, `templates/nes/platformer/`)
- Title (game name, PRESS START) -> stage card -> scrolling stages -> THE END; GAME OVER when
  lives run out (only with the `lives` extra; otherwise retries are unlimited). Start pauses.
- Controls: Left/Right run (accelerates to 2.5 px/frame), A jump (about 3.9 tiles high and
  6 tiles long, release early for a short hop), B = sword (`melee`) or shot (`projectile`),
  Up at a shop sign buys a heart (or a life) for 10 coins.
- Combat: `stomp` jump on enemies; `melee`/`projectile` use B; `none` = avoid enemies.
- Objects: walker (turns at walls and ledges), hopper, flyer, boss (32x32, 3 hits; the goal
  only works after it), coin, heart, life, key (opens doors), shop. Tiles: ground, fill, block,
  one-way platform, spikes (hurt), door (solid until you have the key), decor.
- HUD (sprites, bottom rows): hearts, lives, coins, key, timer - each only when its extra is on.
- Colours follow the stage setting (12 palettes); all art is RetroBake's own (`builders/nes_gfx.py`).
- qa `rom-boot-signature` at `$07FC`: state 1 on the title, 2 from Start onwards.

## Data, not code
`level_blob()` converts game-design's `LevelPack` (`generate_levels(spec)`) into the ROM
layout the 6502 reads directly: config + level table + object lists + uncompressed,
page-aligned 16-byte columns at `$8000-$CFFF` (layout in the header of `main.s`). Other files:
`title.bin` (text records), `str_*.bin` (fixed words), `gfx.chr`. The template `.incbin`s them,
so user text is never parsed by ca65; tool argv is constant.

## Tests
`tests/builders/nes_machine.py` runs baked ROMs on py65 (full 6502) with a PPU/controller
model and can save screenshots (`RETROBAKE_SHOTS=dir`). CI job `nes-bake` runs it, bakes
`baked/sample-hello.nes` and boots it on Mesen + FCEUmm via qa's smoke test.

## Toolchain
`tools/build_cc65.sh`: ca65 + ld65 only, pinned cc65 commit, Linux + mingw-w64 Windows `.exe`,
cc65's zlib `LICENSE`. Release bundles `toolchains/cc65/<platform>/bin` as
`<app>/toolchains/cc65/bin` plus `templates/nes/`.

## Not yet
Sound and music; top-down engine (M3); per-tile background colours (attributes all 0).
