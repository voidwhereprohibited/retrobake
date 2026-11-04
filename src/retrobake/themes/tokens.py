"""Design tokens for RetroBake's own app look.

Clean and modern: a plain sans font, generous spacing and a calm slate
palette. The only retro touch is a soft teal accent. No pixel fonts or
8-bit chrome anywhere in the app UI.
"""

from __future__ import annotations

# Modern sans fonts, first one installed wins. Qt falls back to the system sans.
FONT_FAMILIES = ("Inter", "Segoe UI", "Noto Sans", "Cantarell", "Ubuntu", "DejaVu Sans")

# Spacing scale in pixels (layout only; font sizes are always in points).
SPACE_XS, SPACE_S, SPACE_M, SPACE_L, SPACE_XL = 4, 8, 16, 24, 32
RADIUS_S, RADIUS_M, RADIUS_L = 6, 10, 14

LIGHT = {
    "window": "#F6F7F9",
    "surface": "#FFFFFF",
    "text": "#1C2430",
    "muted": "#4F5B6B",
    "accent": "#0F6E73",  # calm teal, the one subtle retro nod
    "accent_text": "#FFFFFF",
    "border": "#D5DAE1",
    "focus": "#2F6FDB",
}

DARK = {
    "window": "#14181E",
    "surface": "#1D232B",
    "text": "#E9EDF2",
    "muted": "#AAB4C0",
    "accent": "#5CC4C0",
    "accent_text": "#0E1A1C",
    "border": "#38424E",
    "focus": "#7EA8F5",
}
