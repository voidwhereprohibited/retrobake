# RetroBake test plan (owner: qa)

All tests run on GitHub Actions runners (ubuntu-latest + windows-latest) or clean VMs.
Never on Roger's own PC.

## Layers

| Layer | Where | What it proves |
|---|---|---|
| Unit | `tests/<area>/` (pytest, every push) | each module's API and edge cases |
| Boot smoke | `tests/emulator/run_smoke.py` (CI job "Bake sample ROMs + emulator smoke test", Linux + Windows) | every ROM loads, draws, reaches gameplay, never crashes or hangs |
| Bake matrix (M1+, task #9) | same job, `RETROBAKE_SMOKE_ROMS=<dir>` | every genre and every allowed mashup, on NES and SNES |
| Fuzz | `tests/fuzz/test_fuzz_inputs.py` (every push, fixed seeds; `RETROBAKE_FUZZ_N` for longer runs) | junk / huge / hostile wizard text never crashes, hangs, or escapes the sandbox |
| VM checks | clean Ubuntu + Windows VMs, release candidates only | real RetroArch launch (native, Flatpak, Snap, Steam), installer, signatures |

## Boot smoke test

`libretro_harness.py` is a ~200-line stdlib-only (ctypes) headless libretro frontend.
It loads the same cores players use in RetroArch, downloaded fresh in CI from the libretro
buildbot (sha256 logged): NES = Mesen + FCEUmm, SNES = Snes9x. Each ROM x core runs in a
child process with a 120 s timeout, so a crash or hang is a clean FAIL, not a dead runner.

Script per boot: 180 frames idle -> read signature -> hold Start 10 frames -> 180 frames
-> read signature + last frame. A boot passes when:

1. the core loads the ROM and the child exits 0 in time;
2. at least 60 frames are drawn, the frame is at least 200x200, and not all black;
3. RAM holds the boot signature `R B 01 <state>` with state 1 (title) or 2 (gameplay);
4. after Start, state is 2 (gameplay); state 0xEE (fatal error) is always a FAIL.

`selftest_roms.py` builds two tiny hand-assembled reference ROMs (original code, no
assets) that follow the contract. They run on every CI build to prove the harness and
cores work, and are the known-good baseline when an engine ROM fails.

## Boot signature contract (engines must implement)

| System | Address (CPU view) | libretro SYSTEM_RAM offset |
|---|---|---|
| NES | `$07FC-$07FF` | `0x07FC` |
| SNES | `$7E:1FFC-$7E:1FFF` (also `$00:1FFC` mirror) | `0x1FFC` |

Bytes: `0x52 'R'`, `0x42 'B'`, `0x01` (contract version), state:
`0` booting, `1` title screen, `2` gameplay, `0xEE` fatal error.
Write it once init is done; from the title screen, pressing Start must reach state 2
within 180 frames. Reserve these 4 bytes; nothing else may use them.

## Bugs

Filed on the board as `add-task <owner> "bug: ..." "repro steps"`, with the failing
ROM's spec seed and the CI boot-report artifact link. qa signs off merges with
`decide qa "merge <branch>" "approved"` only when CI is green on both OSes.

## Fuzzing

Hostile text (control, bidi, zero-width, zalgo, lone surrogates, 1 MB strings, spaced /
leetspeak / fullwidth / Cyrillic look-alike franchise names, prompt-injection, shell, SQL,
format-string and path tricks) is pushed through every input: `sanitize` for each field,
`check_title`, `style_from_text`, both AI prompts, AI name and image validators, offline art,
both builders' title paths, `safe_filename` and `safe_join`. Only the documented error may be
raised, no call may take over 2 s, and outputs must stay inside their allowlists.
Known bugs are strict `xfail` tests naming their board task: when the fix lands the test
"unexpectedly passes" and CI fails until the marker is removed, so nothing is forgotten.
