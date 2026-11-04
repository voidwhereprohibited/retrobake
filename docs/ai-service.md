# ai-service contract (owner: ai-art)

Package: `retrobake.ai` (`src/retrobake/ai/`). Stdlib only, Windows + Linux. Everything is made
offline on the user's PC: no account, key, online AI or network call (Roger, 11/01: "No AI").

```python
from retrobake.ai import AIService

ai = AIService()
art = ai.make_art(spec, variant=0)  # CoverArt(png, width, height, source, message)
ideas = ai.suggest_names(spec, n=6)  # NameIdeas(names, source, message)
cover = AIService.with_title(art, title)  # final PNG with the title banner
```

- **Never stuck:** `make_art` / `suggest_names` are fast and deterministic. `source` is always
  `"offline"` and `message` is empty; both fields stay so the wizard can show a note later.
- **Threads:** safe from any thread; a worker thread is optional.
- **Try another:** pass `variant=1, 2, ...` for a different picture / set of names.
- **Title:** `with_title` draws the title with RetroBake's own pixel font. It raises
  `InputRejected` (with `.message`) for a title the wizard should not allow.
- **Box shape:** NES 512x704 (portrait), SNES 704x512 (landscape), `cover_size(spec)`.
  The PNG is ready for `retroarch.add_game(..., cover_png=...)` (well under 4 MB).
- **Generator:** `offline_art(spec, variant)` / `offline_names(spec, n, variant)` are deterministic
  from `spec["seed"]` and original-only.
- **Names from text:** `parse_names(lines)` keeps valid, de-duplicated names (longer than 24
  dropped, never truncated; `validate_name` charset + franchise check).

## Security
- No network code, settings or keys. Nothing is cached; results are recomputed from the spec.
- `prompts.py` (fixed templates + `quote_user_text` / `check_prompt`) is kept but not used by
  the service.
