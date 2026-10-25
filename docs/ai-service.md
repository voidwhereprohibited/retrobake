# ai-service contract (owner: ai-art)

Package: `retrobake.ai` (`src/retrobake/ai/`). Stdlib only, plus PySide6's `QImage` to decode AI
pictures (no `QApplication` needed). Windows + Linux.

```python
from retrobake.ai import AIService, AISettings

ai = AIService(AISettings())                 # default: free Pollinations tier, no key
art = ai.make_art(spec, variant=0)           # CoverArt(png, width, height, source, message)
ideas = ai.suggest_names(spec, n=6)          # NameIdeas(names, source, message)
cover = AIService.with_title(art, title)     # final PNG with the title banner
```

- **Never stuck:** `make_art` / `suggest_names` never raise for network, AI or guard problems.
  They return offline results (`source="offline"`) and a plain-English `message` the UI can show
  under the picture. Empty `message` = all good.
- **Threads:** call them from a worker thread (a request can take up to ~2 min; the free tier is
  limited to one request about every 16 s, enforced here).
- **Try another:** pass `variant=1, 2, ...` for a different picture / set of names.
- **Title:** the image model never sees the title; `with_title` draws it with RetroBake's own
  pixel font. It raises `InputRejected` (with `.message`) for a title the wizard should not allow.
- **Box shape:** NES 512x704 (portrait), SNES 704x512 (landscape), `cover_size(spec)`.
  The PNG is ready for `retroarch.add_game(..., cover_png=...)` (well under 4 MB).
- **Offline:** `offline_art(spec, variant)` / `offline_names(spec, n, variant)` are deterministic
  from `spec["seed"]`, original-only, and also used when `AISettings(online=False)`.

## Settings (wizard-ui owns storage; keys stay on the user's PC)

| field | default | meaning |
|---|---|---|
| `online` | `True` | `False` = never use the internet for art/names |
| `provider` | `"pollinations"` | `"pollinations"` free tier (no key), `"pollinations_key"`, `"cloudflare"` |
| `pollinations_key` | `""` | user's own free key from enter.pollinations.ai (optional) |
| `cloudflare_account_id`, `cloudflare_token` | `""` | user's own free Workers AI account (optional backup) |

`repr(AISettings)` never shows keys. A malformed key falls back to offline with a message.

## Endpoints (verified 2026-10-25)

| provider | image | text |
|---|---|---|
| free (default) | `GET https://image.pollinations.ai/prompt/{prompt}?width&height&seed&nologo=true&safe=true&private=true&enhance=false` | `GET https://text.pollinations.ai/{prompt}?system&seed&safe&private&enhance` |
| own key | `GET https://gen.pollinations.ai/image/{prompt}` + `Authorization: Bearer`, `safe=true,sexual,violence` | `GET https://gen.pollinations.ai/text/{prompt}` |
| Cloudflare | `POST .../accounts/{id}/ai/run/@cf/black-forest-labs/flux-1-schnell` → `result.image` base64 | `POST .../@cf/meta/llama-3.1-8b-instruct` → `result.response` |

The anonymous hosts are Pollinations' legacy endpoints; `gen.pollinations.ai` needs a key for
everything. If the anonymous tier ever goes away, users get offline art automatically.

## Security
- Prompts: fixed templates (`prompts.py`), our own words for every spec choice, user story/hero
  text only via `quote_user_text` in two quoted slots, `check_prompt` on the result.
- Network: HTTPS only, host allowlist `ALLOWED_HOSTS`, redirects refused, size caps
  (8 MB image, 16 KB text), timeouts, one retry for 429/5xx only if `Retry-After` <= 30 s.
- Outputs: `validate_image` → QImage decode → crop/pixelate → re-encoded by our PNG writer (drops
  the EXIF/prompt metadata Pollinations embeds). Names: one per line, longer than 24 dropped (never
  truncated), `validate_name` (charset + franchise check), de-duplicated, padded with offline ideas.
- Cache: `%LOCALAPPDATA%\RetroBake\Cache\ai` / `$XDG_CACHE_HOME/retrobake/ai`, sha256 file names
  (never a name from the AI), newest 200 files kept, damaged files ignored.
