"""The ai-service contract: cover art + name ideas that never get the app stuck.

Every public method returns a usable result. When AI is off, offline, busy, blocked by a guard,
or returns anything that fails validation, RetroBake's own offline art / names are used and
``message`` says why in plain English. Call these from a worker thread (network can take ~1 min).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from retrobake.security import InputRejected, OutputRejected, check_title, sanitize, validate_name

from . import offline, prompts
from .compose import decode_art
from .font import add_title_banner
from .providers import Cloudflare, PollinationsFree, PollinationsKey, Provider, ProviderError
from .raster import Canvas, from_png

Source = Literal["ai", "offline"]
CACHE_LIMIT = 200
_NUMBERING = re.compile(r"^\s*(?:[-*\u2022]+|\(?\d{1,2}[.):\]]|[a-hA-H][.)])\s*")


@dataclass
class AISettings:
    online: bool = True
    provider: Literal["pollinations", "pollinations_key", "cloudflare"] = "pollinations"
    pollinations_key: str = ""
    cloudflare_account_id: str = ""
    cloudflare_token: str = ""

    def __repr__(self) -> str:  # never show keys in logs or tracebacks
        return f"AISettings(online={self.online}, provider={self.provider!r})"


@dataclass(frozen=True)
class CoverArt:
    png: bytes  # the picture without the title, PNG, exactly width x height
    width: int
    height: int
    source: Source
    message: str = ""


@dataclass(frozen=True)
class NameIdeas:
    names: list[str]
    source: Source
    message: str = ""


def default_cache_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return base / "RetroBake" / "Cache" / "ai"
    base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "retrobake" / "ai"


def cover_size(spec: dict[str, Any]) -> tuple[int, int]:
    return offline.COVER_SIZE.get(spec.get("system"), offline.COVER_SIZE["nes"])


def _seed(spec: dict[str, Any], variant: int) -> int:
    base = spec.get("seed") if isinstance(spec.get("seed"), int) else 0
    return (base + variant * 7919) & 0x7FFFFFFF


class AIService:
    def __init__(
        self,
        settings: AISettings | None = None,
        *,
        cache_dir: Path | None | bool = None,
        provider: Provider | None = None,
    ) -> None:
        self.settings = settings or AISettings()
        self._provider = provider
        if cache_dir is False:
            self._cache: Path | None = None
        else:
            self._cache = Path(cache_dir) if cache_dir else default_cache_dir()

    # ------------------------------------------------------------------ providers
    def _get_provider(self) -> Provider:
        if self._provider is not None:
            return self._provider
        s = self.settings
        if s.provider == "pollinations_key":
            return PollinationsKey(s.pollinations_key)
        if s.provider == "cloudflare":
            return Cloudflare(s.cloudflare_account_id, s.cloudflare_token)
        return PollinationsFree()

    # ------------------------------------------------------------------ cache
    def _cache_path(self, kind: str, *parts: object) -> Path | None:
        if self._cache is None:
            return None
        digest = hashlib.sha256(json.dumps([kind, *map(str, parts)]).encode()).hexdigest()[:40]
        return self._cache / f"{kind}-{digest}.{'png' if kind == 'art' else 'json'}"

    def _cache_write(self, path: Path | None, data: bytes) -> None:
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(data)
            tmp.replace(path)
            files = sorted(path.parent.glob("*-*.*"), key=lambda p: p.stat().st_mtime)
            for old in files[:-CACHE_LIMIT]:
                old.unlink(missing_ok=True)
        except OSError:
            pass  # a cache is a nice-to-have

    @staticmethod
    def _cache_read(path: Path | None, max_bytes: int) -> bytes | None:
        try:
            if path is None or not path.is_file() or path.stat().st_size > max_bytes:
                return None
            return path.read_bytes()
        except OSError:
            return None

    # ------------------------------------------------------------------ cover art
    def make_art(self, spec: dict[str, Any], *, variant: int = 0) -> CoverArt:
        """Cover picture (no title). Online AI when allowed, else the offline pixel-art cover."""
        width, height = cover_size(spec)
        if not self.settings.online:
            return self._offline_art(spec, variant, "Made by RetroBake (AI pictures are off).")
        try:
            prompt = prompts.cover_prompt(spec)
            provider = self._get_provider()
            path = self._cache_path(
                "art", provider.name, prompt.text, width, height, _seed(spec, variant)
            )
            cached = self._cache_read(path, 4 * 1024 * 1024)
            if cached:
                try:
                    canvas = from_png(cached)
                    if (canvas.width, canvas.height) == (width, height):
                        return CoverArt(cached, width, height, "ai")
                except ValueError:
                    pass  # damaged cache file: fetch again
            raw = provider.image(prompt.text, width=width, height=height, seed=_seed(spec, variant))
            png = decode_art(raw, width, height).to_png()
        except InputRejected as exc:
            return self._offline_art(spec, variant, exc.message)
        except ProviderError as exc:
            return self._offline_art(spec, variant, f"{exc.message} RetroBake drew its own art.")
        except (OutputRejected, ValueError):
            return self._offline_art(
                spec,
                variant,
                "The AI picture didn't pass RetroBake's "
                "safety check, so RetroBake drew its own art.",
            )
        self._cache_write(path, png)
        return CoverArt(png, width, height, "ai")

    @staticmethod
    def _offline_art(spec: dict[str, Any], variant: int, message: str) -> CoverArt:
        canvas = offline.offline_art(spec, variant=variant)
        return CoverArt(canvas.to_png(), canvas.width, canvas.height, "offline", message)

    @staticmethod
    def with_title(art: CoverArt | bytes, title: str) -> bytes:
        """Final cover PNG with the game title banner. Raises InputRejected for a bad title."""
        clean = check_title(sanitize("title", title), field="title")
        png = art.png if isinstance(art, CoverArt) else art
        canvas: Canvas = from_png(png)
        add_title_banner(canvas, clean, bg=(12, 12, 28), fg=(252, 236, 160), shadow=(0, 0, 0))
        return canvas.to_png()

    def cover(
        self, spec: dict[str, Any], title: str, *, variant: int = 0
    ) -> tuple[bytes, CoverArt]:
        art = self.make_art(spec, variant=variant)
        return self.with_title(art, title), art

    # ------------------------------------------------------------------ names
    def suggest_names(self, spec: dict[str, Any], n: int = 6, *, variant: int = 0) -> NameIdeas:
        """``n`` (1-12) original name ideas. The user can always type their own instead."""
        n = max(1, min(12, n))
        if not self.settings.online:
            return NameIdeas(
                offline.offline_names(spec, n, variant=variant),
                "offline",
                "Made by RetroBake (AI ideas are off).",
            )
        try:
            prompt = prompts.names_prompt(spec)
            provider = self._get_provider()
            path = self._cache_path("names", provider.name, prompt.text, _seed(spec, variant))
            cached = self._cache_read(path, 8192)
            names = None
            if cached:
                try:
                    names = parse_names(json.loads(cached))
                except ValueError:
                    names = None
            if not names:
                reply = provider.text(prompt.text, system=prompt.system, seed=_seed(spec, variant))
                names = parse_names(reply.splitlines())
                if names:
                    self._cache_write(path, json.dumps(names).encode())
        except InputRejected as exc:
            return NameIdeas(
                offline.offline_names(spec, n, variant=variant), "offline", exc.message
            )
        except ProviderError as exc:
            return NameIdeas(
                offline.offline_names(spec, n, variant=variant),
                "offline",
                f"{exc.message} Here are RetroBake's own ideas.",
            )
        if not names:
            return NameIdeas(
                offline.offline_names(spec, n, variant=variant),
                "offline",
                "The AI ideas didn't pass RetroBake's checks. Here are its own.",
            )
        names = names[:n]
        seen = {x.casefold() for x in names}
        for extra in offline.offline_names(spec, 12, variant=variant):
            if len(names) >= n:
                break
            if extra.casefold() not in seen:
                names.append(extra)
                seen.add(extra.casefold())
        return NameIdeas(names, "ai")


def parse_names(lines: object) -> list[str]:
    """Validated, de-duplicated names from AI output lines (anything bad is dropped)."""
    if not isinstance(lines, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for line in lines[:40]:
        if not isinstance(line, str):
            continue
        line = _NUMBERING.sub("", line).strip().strip("\"'*`").strip()
        if not line or len(line) > 24:  # never truncate an AI name into something else
            continue
        try:
            name = validate_name(line)
        except OutputRejected:
            continue
        if len(name) < 3 or name.casefold() in seen:
            continue
        seen.add(name.casefold())
        out.append(name)
    return out
