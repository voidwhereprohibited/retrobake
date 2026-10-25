# Contributing to RetroBake

Thanks for wanting to help! RetroBake is built by a small team of AI agents coordinated through a shared task board, plus human contributors like you.

## Ground rules

- **Original content only.** Never add copyrighted characters, names, logos, music or art (Nintendo, Marvel, and so on). A franchise mentioned by a user becomes a *style*, never a copy. This applies to code, templates, tests, screenshots and docs.
- **Free and open source.** No feature may require a paid service, account or API key.
- **Average users first.** The app must never need a terminal. Use plain English in anything a user sees.
- **Windows and Linux are equal.** Test changes on both (CI does this for you).
- **User text is data.** Never put user text into shell commands, assembly or file paths without going through the sanitizer.
- **Keep it light.** Think about download size before adding a dependency.

## Getting set up

You need Python 3.12 or newer.

```
git clone https://github.com/voidwhereprohibited/retrobake.git
```

```
cd retrobake
```

```
python -m pip install -e ".[dev]"
```

```
python -m pytest
```

```
ruff check src tests
```

## Project layout

| Folder | What lives there |
|---|---|
| `src/retrobake/` | The app (Python package) |
| `tests/` | Automated tests |
| `packaging/` | Windows installer and Linux AppImage build files |
| `docs/` | Plan and design notes (`docs/PLAN.md` is the source of truth) |
| `coordination/` | The agent task board |
| `.github/` | CI, security scans and Dependabot |

## Pull requests

1. Fork the repo and create a branch.
2. Keep changes small and focused, with tests.
3. Make sure CI passes (lint, tests on Windows and Linux, dependency audit, CodeQL).
4. Describe what you changed in plain English.

By contributing you agree your work is released under the GPL-3.0 license and that you follow our [Code of Conduct](CODE_OF_CONDUCT.md).

## Security issues

Please report them privately. See [SECURITY.md](SECURITY.md).
