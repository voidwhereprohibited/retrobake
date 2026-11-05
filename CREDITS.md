# Credits

Every art asset RetroBake ships, where it came from, and its license. Rules are in the art
style guide (section 8): original work is GPL-3.0-or-later like the rest of the repo. Add a row
here, or an SPDX header in the file, for anything new.

RetroBake ships no image, font or sound files. All art is drawn by code at runtime, and the
assets below are that code and its data. Covers made on a user's PC are not repo assets.

| Asset | Path in repo | Source URL | License (SPDX) | Author | Used where | Modified? | Added |
|---|---|---|---|---|---|---|---|
| House 5x7 font (the only copy of the glyphs) | src/retrobake/builders/nes_font.py | (original) | GPL-3.0-or-later | Roger (voidwhereprohibited) and RetroBake contributors | NES/SNES ROM titles and cover titles | N and W fixed on 2026-11-04 | — |
| SNES font tiles (made from the house font) | src/retrobake/builders/snes_font.py | (original) | GPL-3.0-or-later | Roger (voidwhereprohibited) and RetroBake contributors | SNES ROM titles | — | — |
| Cover title banner | src/retrobake/ai/font.py | (original) | GPL-3.0-or-later | Roger (voidwhereprohibited) and RetroBake contributors | Cover titles | — | — |
| Offline cover art (procedural scenes and hero sprites) | src/retrobake/ai/offline.py | (original) | GPL-3.0-or-later | Roger (voidwhereprohibited) and RetroBake contributors | Wizard cover art | — | — |
| Curated name ideas | src/retrobake/ai/offline.py (`_NAMES`) | (original) | GPL-3.0-or-later | RetroBake contributors | Wizard name suggestions | — | 2026-11-04 |
| NES ROM template | templates/nes/hello/main.s | (original) | GPL-3.0-or-later | Roger (voidwhereprohibited) and RetroBake contributors | Every NES ROM | — | — |
| SNES ROM template | templates/snes/hello/main.asm | (original) | GPL-3.0-or-later | Roger (voidwhereprohibited) and RetroBake contributors | Every SNES ROM | — | — |
