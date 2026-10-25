# RetroBake 🍞🎮

**Bake your own NES and SNES games — no coding needed.**

[![CI](https://github.com/voidwhereprohibited/retrobake/actions/workflows/ci.yml/badge.svg)](https://github.com/voidwhereprohibited/retrobake/actions/workflows/ci.yml)
[![CodeQL](https://github.com/voidwhereprohibited/retrobake/actions/workflows/codeql.yml/badge.svg)](https://github.com/voidwhereprohibited/retrobake/actions/workflows/codeql.yml)
[![License: GPL-3.0](https://img.shields.io/badge/license-GPL--3.0-blue.svg)](LICENSE)

RetroBake is a free, open-source app for Windows and Linux. Pick a console, pick a genre (or mix two), describe the game you want, answer a few simple questions, and RetroBake builds a real, playable ROM — complete with retro cover art — that you can play right away in RetroArch.

> 🚧 **Status:** early development. Nothing to download yet — watch or star the repo to follow along.

## How it works
1. **Pick a system** — NES or SNES
2. **Pick a genre** — platformer, top-down adventure, and more on the way. Mix two for a mashup.
3. **Describe your game** in your own words
4. **Answer a few questions** — levels, difficulty, hero, setting
5. **Get cover art and name ideas**, made by free AI — or type your own name
6. **Bake it** — RetroBake builds the ROM
7. **Play it** in RetroArch with one click, or save it anywhere

## Planned features
- NES and SNES from day one
- Genre mixing and mashups
- Free AI cover art and title suggestions (no account or API key), with an offline fallback
- One-click **Play in RetroArch**, plus a RetroBake playlist with box art in your RetroArch library
- Runs on Windows and Linux with no terminal or setup
- Built with security in mind: sandboxed builds and sanitized input

## Download
Coming with version 0.1:
- **Windows:** `RetroBake-Setup.exe` — double-click to install.
- **Linux:** `RetroBake.AppImage` — download, allow it to run, double-click.

Downloads will appear on the [Releases page](https://github.com/voidwhereprohibited/retrobake/releases), each with a checksum so you can confirm the file is genuine.

## What you need
- Windows 10/11 or a modern 64-bit Linux
- [RetroArch](https://www.retroarch.com/) (free) to play your games — RetroBake helps you set it up
- An internet connection for AI cover art and name ideas (optional — RetroBake works offline too)

## Original games only
RetroBake makes **original** games. It never includes or produces copyrighted characters, names, or artwork. You can describe a *style* ("an adventure that feels like a classic 8-bit dungeon crawler"), and RetroBake creates original heroes and worlds in that style.

**Disclaimer:** you are responsible for what you create and share with RetroBake. RetroBake is not affiliated with or endorsed by any game company. AI-made art and names can occasionally resemble existing work — check before you share.

## Security
Found a security problem? Please report it privately — see [SECURITY.md](SECURITY.md).

## Contributing
This project is built by a team of AI agents coordinated through a shared task board (`coordination/`), and human contributors are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md), our [Code of Conduct](CODE_OF_CONDUCT.md), and `docs/PLAN.md` for the roadmap.

## License
GPL-3.0. See [LICENSE](LICENSE).
