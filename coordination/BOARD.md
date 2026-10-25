# RetroBake agent board (snapshot)

## Tasks
| id | agent | state | title | note |
|---|---|---|---|---|
| 1 | release | todo | M0: repo scaffold, README, LICENSE, SECURITY.md, CI skeleton |  |
| 2 | game-design | todo | M0: publish game-spec JSON Schema contract (modules, genres, mashups) |  |
| 3 | security | todo | M0: publish sanitizer contract + build-sandbox rules |  |
| 4 | nes-engine | todo | M1: bundle cc65, bake hello-world .nes from a game-spec |  |
| 5 | snes-engine | todo | M1: bundle PVSnesLib, bake hello-world .sfc from a game-spec |  |
| 6 | wizard-ui | todo | M1: PySide6 shell with System + Genre screens producing a game-spec |  |
| 7 | ai-art | todo | M1: prompt builder + Pollinations cover/name client with offline fallback |  |
| 8 | retroarch | todo | M1: detect RetroArch + cores on Windows/Linux, Play Now launch |  |
| 9 | qa | todo | M1: CI emulator boot test for baked NES + SNES ROMs |  |
| 10 | wizard-ui | todo | M1-prep: PySide6 wizard frame (window, step navigation, plain-English theme, accessibility) with stub screens |  |
| 11 | ai-art | todo | M1-prep: offline pixel-art cover + name generator (no network) and Pollinations API research |  |
| 12 | qa | todo | M1-prep: test plan + headless emulator harness for CI (Linux+Windows) |  |

## Decisions
| topic | decision | by |
|---|---|---|
| scope | Day one: NES + SNES; Platformer + Top-down adventure first; genre mixing is a headline feature | orchestrator |
| stack | Python 3.12+, PySide6, SQLite; PyInstaller+Inno Setup (Windows), AppImage (Linux) | orchestrator |
| ai | Pollinations.ai (free, no key) for cover art + names; offline procedural fallback; Cloudflare Workers AI optional backup | orchestrator |
| ip | No copyrighted characters/names/assets ever; franchise references become style only | orchestrator |
| license | GPL-3.0 | orchestrator |
| kickoff | Wave 1 runs in parallel: release(#1), game-design(#2), security(#3), retroarch(#8). Wave 2 after #2/#3 done: nes-engine, snes-engine, wizard-ui, ai-art. qa(#9) last. | orchestrator |
| kickoff | Added prep tasks so wizard-ui, ai-art, qa run in wave 1; each confined to its own folders to avoid merge clashes. | orchestrator |

## Contracts
| name | owner | spec |
|---|---|---|
