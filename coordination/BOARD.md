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

## Decisions
| topic | decision | by |
|---|---|---|
| scope | Day one: NES + SNES; Platformer + Top-down adventure first; genre mixing is a headline feature | orchestrator |
| stack | Python 3.12+, PySide6, SQLite; PyInstaller+Inno Setup (Windows), AppImage (Linux) | orchestrator |
| ai | Pollinations.ai (free, no key) for cover art + names; offline procedural fallback; Cloudflare Workers AI optional backup | orchestrator |
| ip | No copyrighted characters/names/assets ever; franchise references become style only | orchestrator |
| license | GPL-3.0 | orchestrator |

## Contracts
| name | owner | spec |
|---|---|---|
