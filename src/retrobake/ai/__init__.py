"""RetroBake cover art + name ideas (owned by the ai-art agent). Offline only, no network.

Contract (docs/ai-service.md)::

    from retrobake.ai import AIService
    ai = AIService()
    art = ai.make_art(spec, variant=0)              # CoverArt(png, width, height, source, message)
    ideas = ai.suggest_names(spec, n=6)             # NameIdeas(names, source, message)
    cover_png = ai.with_title(art, "Frost Dash")    # final box art with the title banner
"""

from __future__ import annotations

from .offline import COVER_SIZE, offline_art, offline_names
from .service import AIService, CoverArt, NameIdeas, cover_size, parse_names

__all__ = [
    "COVER_SIZE",
    "AIService",
    "CoverArt",
    "NameIdeas",
    "cover_size",
    "offline_art",
    "offline_names",
    "parse_names",
]
