# RetroBake — Project Plan

**One line:** a free, open-source desktop app (Windows + Linux) where an average, non-technical person picks a system, picks one genre, describes their game, answers a few guided questions, and RetroBake "bakes" a real playable NES or SNES ROM — with AI-made cover art and name ideas — then launches it in RetroArch or saves it wherever they want.

Owner: Roger (GitHub: voidwhereprohibited). Repo: voidwhereprohibited/retrobake (separate from PenguinPort).

## Who it's for
- Average users, not tinkerers. No terminal, no code, no setup knowledge.
- Most users on Windows; Roger runs Ubuntu. Both must be first-class.

## Day-one scope
- Systems: **NES and SNES** from day one.
- Genres (most popular first): **Platformer** and **Top-down action-adventure** first; then RPG, shooter, puzzle, sports.
- **One genre per game.** Each game is exactly one genre; ready-made templates (e.g. action-adventure) and optional "inspirations" only tune it, never blend genres.

## User flow (the wizard)
1. Pick a system (NES / SNES).
2. Pick one genre from a drop-down.
3. Describe the game in plain words.
4. Answer guided follow-up questions specific to the chosen genre(s) (e.g. how many levels/dungeons, difficulty, hero type, setting, color mood).
5. AI makes cover art and suggests names; user picks one or types their own.
6. RetroBake builds the ROM from tested engine templates.
7. Finish screen: **Play now in RetroArch**, **Save ROM to...**, **Save cover art**, **Add to RetroArch library**.

## How games get built
- Never generate free-form assembly. Games are assembled from **tested, modular engine pieces** filled with data:
  - Movement: side-scrolling jump / top-down walk / free-flight
  - Combat: stomp / melee swing / projectile
  - Progression: linear levels / open map / dungeons + items
  - Extras: hearts/HP, lives, collectibles, bosses, keys/doors
- A template = a hand-tuned set of pieces for one genre (e.g. action-adventure: side-scrolling movement + dungeon progression + sword combat + hearts).
- NES toolchain: **cc65/ca65** (nesdoug/neslib style templates, NROM/UNROM mapper).
- SNES toolchain: **PVSnesLib** (816-tcc / wla-dx).
- Toolchains are bundled with the app so users install nothing.

## Cover art and names (offline, no AI)
- Decision (Roger, 11/01): "No AI". RetroBake needs no account, key or online service.
- Cover art: procedural pixel-art cover from the wizard answers + RetroBake's title font, made on the user's PC.
- Names: original name ideas built offline from the wizard answers; the user can always type their own.
- Optional, later: in-game sprite/tileset generation, reduced to NES/SNES palettes and tile limits.

## RetroArch integration
- Detect RetroArch install (Windows + Linux incl. Flatpak/Snap/Steam).
- Launch with correct core: NES → Mesen / FCEUmm / Nestopia; SNES → Snes9x / bsnes.
- Write a "RetroBake" playlist (.lpl) and drop cover art into thumbnails so games show up in the library.
- Rebake → relaunch loop for quick testing.
- Setup helper if RetroArch or a core is missing.

## Rules that never bend
- **No copyrighted characters, names, logos or assets** (Nintendo, Marvel, etc.). Users can say "like Zelda" — RetroBake turns that into the *style* with original heroes. Menus never list franchises; no franchise names in marketing.
- **Free and open source.** No paid services required.
- **Lightweight app.** Small images, bundled toolchains only.
- **Security is top-notch** (see below).
- Never test on Roger's own PC — use CI and clean VMs.

## Security (approved five-part plan)
1. **Input cleanup:** length limits, strip control/odd characters, user text is data only, never executed or interpolated into build scripts.
2. **AI guarding:** user text wrapped in a fixed prompt template (anti-injection), outputs validated (image size/type, name length/charset).
3. **Sandboxed builds:** only our templates, temp working dir, no shell interpolation, size + time limits, no network during build.
4. **Safe releases:** signed builds, dependency scanning (Dependabot/pip-audit), CodeQL, SECURITY.md for private reports.
5. **Disclaimer:** users are responsible for what they create (README + in-app).

## Tech stack
- Python 3.12+, **PySide6** (Qt) GUI — native on Windows and Linux.
- SQLite for local projects/history.
- Packaging: PyInstaller → Windows installer (Inno Setup) + Linux AppImage (Flatpak later).
- GitHub Actions CI: tests, lint, security scans, build both platforms, emulator smoke test of baked ROMs.

## Milestones
- **M0** Repo, CI, agent board, README, license (GPL-3.0, matches cc65/PVSnesLib ecosystems — confirm).
- **M1** Toolchains bundled; "hello world" NES + SNES ROM baked from the app.
- **M2** Platformer engine NES + SNES, wizard v1.
- **M3** Top-down adventure engine; action-adventure template v1.
- **M4** Offline cover art + name ideas (no AI, no account, no network).
- **M5** RetroArch Play Now, playlist, thumbnails, setup helper.
- **M6** Security hardening + signed Windows installer + AppImage; public v0.1.
