"""AI providers: Pollinations free tier (default, no key), Pollinations with the user's own key,
and Cloudflare Workers AI (optional backup, user's own free account).

Network rules: HTTPS only, fixed host allowlist, no redirects, hard size caps and timeouts.
Nothing here ever runs during a build. Keys are never logged or put in error messages.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from retrobake import __version__ as _app_version
from retrobake.security import POLLINATIONS_REQUIRED_PARAMS

ALLOWED_HOSTS = frozenset(
    {"image.pollinations.ai", "text.pollinations.ai", "gen.pollinations.ai", "api.cloudflare.com"}
)
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_TEXT_BYTES = 16 * 1024
IMAGE_TIMEOUT = 120.0
TEXT_TIMEOUT = 60.0
FREE_TIER_INTERVAL = 16.0  # anonymous Pollinations: about one request per 15 s per IP
MAX_WAIT = 30.0
USER_AGENT = f"RetroBake/{_app_version} (+https://github.com/voidwhereprohibited/retrobake)"
# gen.pollinations.ai: safe=true only covers privacy+secrets; add the content filters.
GEN_SAFE = "true,sexual,violence"

_KEY_RE = re.compile(r"^[A-Za-z0-9_\-]{8,200}$")
_CF_ACCOUNT_RE = re.compile(r"^[a-f0-9]{32}$")


class ProviderError(Exception):
    """An AI request failed. ``message`` is plain English and safe to show."""

    def __init__(self, message: str, *, status: int = 0) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


@dataclass
class HttpResponse:
    status: int
    body: bytes
    headers: dict[str, str] = field(default_factory=dict)


class Transport(Protocol):
    def __call__(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout: float,
        max_bytes: int,
    ) -> HttpResponse: ...


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return None  # a 3xx becomes an HTTPError; we never follow it


_OPENER = urllib.request.build_opener(_NoRedirect())


def check_url(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or parts.hostname not in ALLOWED_HOSTS or parts.username:
        raise ProviderError("RetroBake blocked an unexpected web address.")
    return url


def urllib_transport(
    method: str,
    url: str,
    headers: dict[str, str],
    body: bytes | None,
    timeout: float,
    max_bytes: int,
) -> HttpResponse:
    req = urllib.request.Request(check_url(url), data=body, headers=headers, method=method)  # noqa: S310
    try:
        with _OPENER.open(req, timeout=timeout) as resp:
            data = resp.read(max_bytes + 1)
            return HttpResponse(resp.status, data, {k.lower(): v for k, v in resp.headers.items()})
    except urllib.error.HTTPError as exc:
        data = exc.read(4096) if exc.fp else b""
        hdrs = {k.lower(): v for k, v in (exc.headers or {}).items()}
        return HttpResponse(exc.code, data, hdrs)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ProviderError("Couldn't reach the art service. Check your internet.") from exc


class Provider:
    name = "base"
    free_tier = False

    def __init__(
        self,
        transport: Transport | None = None,
        *,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._transport = transport or urllib_transport
        self._sleep = sleep
        self._clock = clock

    # -- shared request logic -------------------------------------------------
    def _request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: float,
        max_bytes: int,
    ) -> HttpResponse:
        hdrs = {"User-Agent": USER_AGENT, **(headers or {})}
        for attempt in range(2):
            self._throttle()
            resp = self._transport(method, check_url(url), hdrs, body, timeout, max_bytes)
            if resp.status == 200:
                if len(resp.body) > max_bytes:
                    raise ProviderError("The art service sent back too much data.", status=200)
                return resp
            if attempt == 0 and resp.status in (429, 500, 502, 503, 504):
                wait = _retry_after(resp.headers.get("retry-after"), 3.0)
                if wait <= MAX_WAIT:
                    self._sleep(wait)
                    continue
            break
        raise ProviderError(_status_message(resp.status), status=resp.status)

    def _throttle(self) -> None:
        if not self.free_tier:
            return
        with _FREE_LOCK:
            now = self._clock()
            wait = _FREE_STATE["next"] - now
            if wait > MAX_WAIT:
                raise ProviderError("The free art service is busy. Try again in a minute.")
            if wait > 0:
                self._sleep(wait)
                now += wait
            _FREE_STATE["next"] = now + FREE_TIER_INTERVAL

    def image(self, prompt: str, *, width: int, height: int, seed: int) -> bytes:
        raise NotImplementedError

    def text(self, prompt: str, *, system: str, seed: int) -> str:
        raise NotImplementedError


_FREE_LOCK = threading.Lock()
_FREE_STATE = {"next": 0.0}


def _retry_after(value: str | None, default: float) -> float:
    try:
        return max(0.0, float(value)) if value else default
    except ValueError:
        return MAX_WAIT + 1


def _status_message(status: int) -> str:
    if status in (401, 403):
        return "The art service didn't accept the key in Settings."
    if status == 402:
        return "Your art service allowance is used up for now."
    if status == 429:
        return "The free art service is busy. Try again in a minute."
    if status == 400:
        return "The art service couldn't use this description."
    return "The art service had a problem. RetroBake made its own art instead."


def _q(text: str) -> str:
    return urllib.parse.quote(text, safe="")


def _decode_text(body: bytes) -> str:
    return body[:MAX_TEXT_BYTES].decode("utf-8", errors="replace")


class PollinationsFree(Provider):
    """Pollinations anonymous tier: no key, no account. Rate-limited, may change any time."""

    name = "pollinations"
    free_tier = True

    def image(self, prompt: str, *, width: int, height: int, seed: int) -> bytes:
        params = {
            "width": width,
            "height": height,
            "seed": seed,
            "nologo": "true",
            **POLLINATIONS_REQUIRED_PARAMS,
        }
        url = f"https://image.pollinations.ai/prompt/{_q(prompt)}?{urllib.parse.urlencode(params)}"
        return self._request("GET", url, timeout=IMAGE_TIMEOUT, max_bytes=MAX_IMAGE_BYTES).body

    def text(self, prompt: str, *, system: str, seed: int) -> str:
        params = {"system": system, "seed": seed, **POLLINATIONS_REQUIRED_PARAMS}
        url = f"https://text.pollinations.ai/{_q(prompt)}?{urllib.parse.urlencode(params)}"
        resp = self._request("GET", url, timeout=TEXT_TIMEOUT, max_bytes=MAX_TEXT_BYTES)
        return _decode_text(resp.body)


class PollinationsKey(Provider):
    """gen.pollinations.ai with the user's own free Pollinations key (sk_...)."""

    name = "pollinations_key"

    def __init__(self, key: str, transport: Transport | None = None, **kw) -> None:  # noqa: ANN003
        super().__init__(transport, **kw)
        if not _KEY_RE.match(key or ""):
            raise ProviderError("The Pollinations key in Settings doesn't look right.")
        self._auth = {"Authorization": f"Bearer {key}"}

    def _params(self, **extra: object) -> str:
        return urllib.parse.urlencode({**extra, **POLLINATIONS_REQUIRED_PARAMS, "safe": GEN_SAFE})

    def image(self, prompt: str, *, width: int, height: int, seed: int) -> bytes:
        url = f"https://gen.pollinations.ai/image/{_q(prompt)}?" + self._params(
            width=width, height=height, seed=seed
        )
        return self._request(
            "GET", url, headers=self._auth, timeout=IMAGE_TIMEOUT, max_bytes=MAX_IMAGE_BYTES
        ).body

    def text(self, prompt: str, *, system: str, seed: int) -> str:
        url = f"https://gen.pollinations.ai/text/{_q(prompt)}?" + self._params(
            system=system, seed=seed
        )
        resp = self._request(
            "GET", url, headers=self._auth, timeout=TEXT_TIMEOUT, max_bytes=MAX_TEXT_BYTES
        )
        return _decode_text(resp.body)


class Cloudflare(Provider):
    """Cloudflare Workers AI REST API with the user's own free account id + API token."""

    name = "cloudflare"
    IMAGE_MODEL = "@cf/black-forest-labs/flux-1-schnell"
    TEXT_MODEL = "@cf/meta/llama-3.1-8b-instruct"

    def __init__(
        self, account_id: str, token: str, transport: Transport | None = None, **kw
    ) -> None:  # noqa: ANN003
        super().__init__(transport, **kw)
        if not _CF_ACCOUNT_RE.match(account_id or "") or not _KEY_RE.match(token or ""):
            raise ProviderError(
                "The Cloudflare account ID or token in Settings doesn't look right."
            )
        self._base = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/"
        self._auth = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def _run(self, model: str, payload: dict, max_bytes: int, timeout: float) -> dict:
        body = json.dumps(payload).encode()
        resp = self._request(
            "POST",
            self._base + model,
            headers=self._auth,
            body=body,
            timeout=timeout,
            max_bytes=max_bytes,
        )
        try:
            data = json.loads(resp.body)
        except ValueError as exc:
            raise ProviderError("The art service sent back something unexpected.") from exc
        result = data.get("result") if isinstance(data, dict) else None
        if not isinstance(result, dict):
            raise ProviderError("The art service sent back something unexpected.")
        return result

    def image(self, prompt: str, *, width: int, height: int, seed: int) -> bytes:
        # flux-1-schnell has no size option (square); RetroBake crops it to the box shape.
        result = self._run(
            self.IMAGE_MODEL,
            {"prompt": prompt, "steps": 4, "seed": seed},
            MAX_IMAGE_BYTES * 4 // 3 + 4096,
            IMAGE_TIMEOUT,
        )
        b64 = result.get("image")
        if not isinstance(b64, str):
            raise ProviderError("The art service sent back no picture.")
        try:
            return base64.b64decode(b64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ProviderError("The art service sent back a broken picture.") from exc

    def text(self, prompt: str, *, system: str, seed: int) -> str:
        payload = {
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 200,
            "seed": seed,
        }
        result = self._run(self.TEXT_MODEL, payload, MAX_TEXT_BYTES, TEXT_TIMEOUT)
        text = result.get("response")
        if not isinstance(text, str):
            raise ProviderError("The art service sent back no names.")
        return text[:MAX_TEXT_BYTES]
