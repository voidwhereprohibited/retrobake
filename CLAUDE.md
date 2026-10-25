# RetroBake — shared rules for every agent

Read `docs/PLAN.md` first. It is the source of truth for scope and rules.

## The central database (agent board)
Every agent coordinates through one SQLite database: `coordination/retrobake.db` in the main checkout, driven by `coordination/board.py`. Agents run in separate git worktrees, but board.py always resolves to the same database file. `coordination/BOARD.md` is the readable snapshot committed to git (`board.py export`).

Run an agent: `coordination/run_agent.sh <agent> "<task>"` (headless, own worktree, logs in `coordination/logs/`).

**At the start of every job:**
```
python3 coordination/board.py inbox <your-agent-name>
python3 coordination/board.py tasks --agent <your-agent-name>
python3 coordination/board.py contracts
```
**While working:** `claim` a task before starting it; set `blocked` with a note if you need another agent, and send that agent a `note --to`.
**When you finish:**
- `set-state <id> done "what changed + file paths"`
- `decide` for any design choice other agents must follow
- `contract` for any interface others build on (file formats, Python APIs, JSON schemas, folder layout)
- `note --to <agent>` to hand off follow-up work, or `add-task` for them

Never change another agent's published contract without a `note` to its owner and a new `decide` entry.

## Agent roster
| Agent | Owns |
|---|---|
| orchestrator | breaks milestones into tasks, assigns, unblocks, merges, keeps PLAN.md current |
| wizard-ui | PySide6 app, wizard screens, drop-downs, finish screen |
| game-design | the "game spec" JSON schema, genre modules, mashup rules, guided questions |
| nes-engine | cc65 engine templates + NES builder |
| snes-engine | PVSnesLib engine templates + SNES builder |
| ai-art | Pollinations cover art + name suggestions, prompt builder, offline fallback |
| retroarch | RetroArch detection, Play Now, playlists, thumbnails, setup helper |
| security | input cleanup, prompt guarding, build sandbox, IP guard, CI scans |
| release | packaging (Windows installer, AppImage), CI, signing, README/docs |
| qa | tests, emulator smoke tests, VM testing, bug filing on the board |

## Hard rules
- No copyrighted characters, names, logos or assets. Ever. Franchise names in user text are turned into *style*, never reproduced.
- Free + open source only. No paid service required to use the app.
- Average-user first: no terminal, plain-English UI, no jargon.
- Windows and Linux both first-class.
- Never run tests or install test apps on Roger's own PC — use CI or a clean VM.
- User text is data. Never execute it, never put it into shell commands or assembly unescaped.
- Commit messages: short, present tense. Don't push to `main` without the orchestrator's merge.
