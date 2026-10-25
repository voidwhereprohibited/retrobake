"""RetroBake's own 5x7 font as SNES 2bpp tiles (same glyphs as the NES font).

Same charset and tile numbering as ``nes_font``: tile N = CHARSET[N], tile 0 = blank space,
lowercase drawn uppercase. SNES 2bpp stores each row as (plane0, plane1) byte pairs, while
NES CHR stores 8 plane-0 rows then 8 plane-1 rows, so this only re-interleaves the bytes.
"""

from __future__ import annotations

from . import nes_font

CHARSET = nes_font.CHARSET
TILE_BYTES = 16


def _to_2bpp(nes_tile: bytes) -> bytes:
    lo, hi = nes_tile[:8], nes_tile[8:16]
    return bytes(b for pair in zip(lo, hi, strict=True) for b in pair)


def font_bin() -> bytes:
    """All glyph tiles, packed: len(CHARSET) * 16 bytes."""
    bank = nes_font.chr_bank()
    tiles = len(CHARSET)
    return b"".join(_to_2bpp(bank[i * 16 : i * 16 + 16]) for i in range(tiles))


def tiles_for(text: str) -> bytes:
    """Tile numbers for ``text``. Raises ValueError on characters the font lacks."""
    return nes_font.tiles_for(text)
