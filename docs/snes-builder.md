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
  - Runs `retrobake.spec.validate`, then `security.sanitize("title")` + `check_title`, then
    wla-65816 + wlalink through `security.run_build` in a `BuildWorkspace`, then patches the
    internal header name (title in plain uppercase ASCII) and rewrites the checksum.
    Deterministic: the same spec always gives byte-identical ROMs.
- `SnesBuildError(message, detail)` - the only error `bake` raises. `message` is plain English
  for the UI; `detail` is tool output for logs/bug reports.
- `find_wladx(wla_dir=None) -> Path` - toolchain folder. Search order: argument,
  `RETROBAKE_WLA_DIR`, `<app>/toolchains/pvsneslib/bin`,
  `<app>/toolchains/pvsneslib/<linux|windows>/bin` (`<app>` = PyInstaller `_MEIPASS` when
  frozen, else the repo root).
- `templates_dir()` = `<app>/templates/snes`. `check_rom(rom)` checks size, LoROM map byte,
  checksum/complement and reset vector. `checksum(rom)`, `header_name(title)`.
- Constants: `ROM_BYTES` (32768), `MAPPER` ("LoROM"), `ENGINE`, `HEADER` ($7FC0), row numbers.

## M1 output ("hello" engine)
32 KB LoROM, SlowROM, NTSC, no SRAM. BG mode 0, BG1 2bpp. Title centred on row 10,
"PRESS START" on row 15, "MADE WITH RETROBAKE" on row 24, white on dark blue, same original
5x7 font as the NES (`builders/snes_font.py` re-interleaves `nes_font` tiles into SNES 2bpp).
Boot signature (qa contract `rom-boot-signature`) at WRAM $7E:1FFC: "RB", v1, state 1 on the
title screen; Start sets state 2 (gameplay) and turns the backdrop dark green. Stack sits at
$1EFF so it never touches the signature.

## Safety
- The template (`templates/snes/hello/main.asm`, `linkfile`) is fixed code. The builder writes
  only binary data files (`text.bin` records `[len, vram_lo, vram_hi, tiles...]`, 0-ended,
  and `font.bin`) that the template `.INCBIN`s, so user text is never parsed as assembly.
  Tool argv is constant. The header name is patched into the linked image as data.

## Toolchain
`tools/build_snes_toolchain.sh` builds wla-65816 + wlalink only, from the exact WLA-DX commit
PVSnesLib 4.6.0 pins (`compiler/wla-dx` = 6fa1f673), native Linux + static mingw-w64 Windows
`.exe` (cross build imports the native instruction-table generators), into
`toolchains/pvsneslib/{linux,windows}/bin` with WLA-DX's `LICENSE` (GPL-2.0-or-later).
CI job `snes-toolchain` builds/caches it; `snes-bake` runs the builder tests, bakes
`tools/bake_sample_snes.py`, and boots it on the Snes9x libretro core with qa's smoke test, on
Ubuntu and Windows. Release bundles the matching folder as `toolchains/pvsneslib/bin` plus
`templates/snes/`. 816-tcc, 816-opt, constify and the PVSnesLib library (MIT) are added from
the same 4.6.0 release when an engine module needs C (M2+).
