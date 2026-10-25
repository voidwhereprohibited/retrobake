# RetroBake safety layer (security agent contract)

Package: `retrobake.security` (stdlib only, Windows + Linux). Every agent uses it; nobody
writes their own input cleaning, prompt building safety or subprocess calls.

## 1. User input — `sanitize(field, text)`
| Field | Max | Rule |
|---|---|---|
| `title`, `name_idea` | 24 | ASCII letters/numbers + `. , ! ? ' & : -` (accents folded: Café → Cafe) |
| `description` | 500 | any language, multi-line |
| `hero_description` | 120 | one line |
| `answer` | 80 | free-text guided answers |
| `style_tag` | 24 | `^[a-z][a-z_]{1,23}$` |

Pipeline: cap → NFKC → drop control/format/private/unassigned chars (NUL, bidi overrides,
zero-width) → max 2 accents per letter → collapse spaces → cap → allowlist.
Raises `InputRejected`; show `exc.message` (plain English). Drop-downs: `clean_choice(value, allowed)`.
Files: `safe_filename(name, ext)` (no paths, no Windows reserved names), `safe_join(base, *parts)`.
Limits mirror `src/retrobake/spec/game_spec.schema.json`; change both together.

## 2. IP guard — no franchise names anywhere
- `check_title(text)` for titles, name ideas, menu text: rejects any listed name (strict).
- `scrub_ip(text)` for free text going into prompts: replaces names with "a classic game".
- `find_ip(text)` to just look. Matching ignores case, accents, Cyrillic/Greek look-alikes,
  leetspeak (`Mar1o`), spacing (`M a r i o`, `SuperMario`) and suffixes (`Nintendo64`).
- List: `src/retrobake/security/ip_blocklist.json` (`terms` always; `ambiguous` everyday words
  like toad/link/sonic only when a real name is also present, always in titles; `allow` genre
  words like metroidvania). Style words are fine. Add names by PR to security.

## 3. AI guarding (ai-art)
1. Fixed prompt template in code, single-spaced; user text only fills slots.
2. Each slot: `quote_user_text(text)` → cleaned, IP-scrubbed, instruction/URL/markup removed, quoted.
3. Whole prompt: `check_prompt(prompt)` right before the request.
4. Every request includes `POLLINATIONS_REQUIRED_PARAMS` (`safe=true`, `private=true`, `enhance=false`).
   On the keyed `gen.pollinations.ai` host `safe=true` only means privacy+secrets, so `safe` there
   must be `POLLINATIONS_GEN_SAFE` (`true,sexual,violence`). The anonymous image host embeds the
   prompt in EXIF, so AI images are always re-encoded before saving (ai-art does this).
5. Results: `validate_name(text)` and `validate_image(bytes)` (PNG/JPEG/WebP, ≤ 8 MB,
   64–2048 px), then decode with QImage, passing the format `validate_image` returned. Any `OutputRejected` → offline fallback.
   Never use a file name or URL from the AI response.

## 4. Build sandbox (nes-engine, snes-engine)
```python
with BuildWorkspace([TEMPLATES_DIR]) as ws:
    ws.copy_template(TEMPLATES_DIR / "nes/platformer", "src")
    ws.write_file("src/level_data.s", generated_text)   # data only
    res = run_build([CC65_BIN / "cl65", "-t", "nes", "-o", "game.nes", "src/main.s"],
                    workspace=ws, toolchain_dirs=[CC65_BIN])
    rom = ws.read_output("game.nes", max_bytes=1024 * 1024)
```
- Argument lists only (never `shell=True`); argv[0] must be inside a bundled toolchain folder.
- User text never goes in argv or raw assembly; only as escaped data the builder generates
  (strings as `.byte` values from the cleaned ASCII title, never inline source).
- Clean env (PATH = toolchain dirs, HOME/TMP = workspace, proxies → dead address).
- Limits (`BuildLimits`): 120 s, 1 GB memory, 16 MB per file, 128 MB workspace, 256 KB log.
  Linux: `prlimit`; Windows: kill-on-close Job Object (memory + process count). The tool is
  started suspended and only resumed once it is inside the job, so nothing it starts escapes.
  Whole tree killed on timeout and after every run. Workspace deleted afterwards (retried on
  Windows while killed tools release their files; a cleanup failure never hides the real error).
- Network: Linux uses an empty network namespace when the OS allows it (Ubuntu 24.04+
  blocks unprivileged ones via AppArmor, so it may be off); the bundled toolchains have no
  network code, which is the guarantee. `BuildResult.network_isolated` reports which.

## 5. Releases
CodeQL, pip-audit and Dependabot run in CI (release). Signed builds at M6. Disclaimer text:
`retrobake.security.DISCLAIMER` / `DISCLAIMER_SHORT` — wizard-ui shows it on first run and
the finish screen; README carries the same text.

## Severity
High (blocks merge): user text reaching a shell/argv/assembly unescaped, `shell=True`, a
franchise name in any output, AI output used unvalidated, network calls during a build.
