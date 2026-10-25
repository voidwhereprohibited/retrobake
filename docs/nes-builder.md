# NES builder (contract `nes-builder`, owner: nes-engine)

```python
from retrobake.builders import nes

result = nes.bake(spec)            # spec = validated game-spec dict, system "nes"
rom_bytes = result.rom             # complete iNES file, write it with a .nes extension
```

## API
- `bake(spec, *, cc65_dir=None, limits=None) -> NesRom`
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

## Safety
- The template (`templates/nes/hello/main.s`, `nrom.cfg`) is fixed code. The builder writes
  only binary data files (`text.bin` tile records, `font.chr`) that the template `.incbin`s,
  so user text is never parsed as assembly. Tool argv is constant.

## Toolchain
`tools/build_cc65.sh` builds ca65 + ld65 only (no C compiler/libraries: lighter) from a pinned
cc65 commit, native Linux + mingw-w64 Windows `.exe`, into `toolchains/cc65/{linux,windows}/bin`
with cc65's zlib `LICENSE`. CI job `cc65` builds/caches it and hands it to the test jobs;
release bundles the matching folder as `toolchains/cc65/bin` plus `templates/nes/`.
