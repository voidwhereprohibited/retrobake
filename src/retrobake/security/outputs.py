"""Validate everything that comes back from an AI service before RetroBake uses it."""

from __future__ import annotations

import struct

from .errors import InputRejected, OutputRejected
from .ipguard import check_title
from .sanitizer import sanitize

MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_SIDE = 2048
MIN_SIDE = 64


def validate_name(text: object) -> str:
    """An AI name idea -> clean title-safe string, or OutputRejected."""
    if not isinstance(text, str):
        raise OutputRejected("name is not text")
    lines = text.strip().splitlines()
    candidate = lines[0].strip().strip("\"'*").strip() if lines else ""
    try:
        return check_title(sanitize("name_idea", candidate), field="name_idea")
    except InputRejected as exc:
        raise OutputRejected(exc.message) from exc


def _png_size(data: bytes) -> tuple[int, int]:
    if len(data) < 24 or data[12:16] != b"IHDR":
        raise OutputRejected("bad PNG header")
    return struct.unpack(">II", data[16:24])


def _jpeg_size(data: bytes) -> tuple[int, int]:
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            raise OutputRejected("bad JPEG marker")
        marker = data[i + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        (seg_len,) = struct.unpack(">H", data[i + 2 : i + 4])
        if seg_len < 2:
            raise OutputRejected("bad JPEG segment")
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            h, w = struct.unpack(">HH", data[i + 5 : i + 9])
            return w, h
        i += 2 + seg_len
    raise OutputRejected("JPEG has no size")


def _webp_size(data: bytes) -> tuple[int, int]:
    chunk = data[12:16]
    if chunk == b"VP8 " and len(data) >= 30:
        w, h = struct.unpack("<HH", data[26:30])
        return w & 0x3FFF, h & 0x3FFF
    if chunk == b"VP8L" and len(data) >= 25:
        b = data[21:25]
        w = 1 + (((b[1] & 0x3F) << 8) | b[0])
        h = 1 + (((b[3] & 0x0F) << 10) | (b[2] << 2) | ((b[1] & 0xC0) >> 6))
        return w, h
    if chunk == b"VP8X" and len(data) >= 30:
        w = 1 + int.from_bytes(data[24:27], "little")
        h = 1 + int.from_bytes(data[27:30], "little")
        return w, h
    raise OutputRejected("bad WebP header")


def validate_image(data: object) -> tuple[str, int, int]:
    """Check AI cover art bytes. Returns (kind, width, height); kind is png, jpeg or webp.

    Only the file header is trusted here; decode it with Qt (QImage) afterwards and treat a
    decode failure as OutputRejected too. Never save the bytes under a name the AI chose.
    """
    if not isinstance(data, bytes | bytearray):
        raise OutputRejected("image is not bytes")
    data = bytes(data)
    if not 0 < len(data) <= MAX_IMAGE_BYTES:
        raise OutputRejected("image is empty or too big")
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        kind, (w, h) = "png", _png_size(data)
    elif data.startswith(b"\xff\xd8\xff"):
        kind, (w, h) = "jpeg", _jpeg_size(data)
    elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        kind, (w, h) = "webp", _webp_size(data)
    else:
        raise OutputRejected("not a PNG, JPEG or WebP image")
    if not (MIN_SIDE <= w <= MAX_SIDE and MIN_SIDE <= h <= MAX_SIDE):
        raise OutputRejected(f"image size {w}x{h} is out of range")
    return kind, w, h
