"""RetroBake AI features (owned by the ai-art agent): cover art + name ideas.

Contract (docs/ai-service.md)::

    from retrobake.ai import AIService, AISettings
    ai = AIService(AISettings())               # free Pollinations tier, no key
    art = ai.make_art(spec, variant=0)         # CoverArt(png, width, height, source, message)
    ideas = ai.suggest_names(spec, n=6)        # NameIdeas(names, source, message)
    cover_png = ai.with_title(art, "Frost Dash")   # final box art with the title banner

Nothing here raises for network/AI problems; results fall back to offline art and names.
"""

from __future__ import annotations

from .offline import COVER_SIZE, offline_art, offline_names
from .providers import ALLOWED_HOSTS, ProviderError
from .service import (
    AIService,
    AISettings,
    CoverArt,
    NameIdeas,
    cover_size,
    default_cache_dir,
    parse_names,
)

__all__ = [
    "ALLOWED_HOSTS",
    "COVER_SIZE",
    "AIService",
    "AISettings",
    "CoverArt",
    "NameIdeas",
    "ProviderError",
    "cover_size",
    "default_cache_dir",
    "offline_art",
    "offline_names",
    "parse_names",
]
