"""Tiny RGB canvas + PNG writer/reader (stdlib only).

Used for the offline cover, the title banner and for re-encoding AI art (which also strips any
metadata the AI service embedded). Only reads PNGs this module wrote (8-bit RGB, filter 0).
"""

from __future__ import annotations

import struct
import zlib

Color = tuple[int, int, int]

_SIG = b"\x89PNG\r\n\x1a\n"
MAX_SIDE = 4096


class Canvas:
    __slots__ = ("width", "height", "data")

    def __init__(self, width: int, height: int, fill: Color = (0, 0, 0)) -> None:
        if not (0 < width <= MAX_SIDE and 0 < height <= MAX_SIDE):
            raise ValueError("canvas size out of range")
        self.width = width
        self.height = height
        self.data = bytearray(bytes(fill) * (width * height))

    @classmethod
    def from_rgb(cls, width: int, height: int, rgb: bytes) -> Canvas:
        if len(rgb) != width * height * 3:
            raise ValueError("pixel data does not match size")
        c = cls(width, height)
        c.data[:] = rgb
        return c

    def get(self, x: int, y: int) -> Color:
        i = (y * self.width + x) * 3
        return self.data[i], self.data[i + 1], self.data[i + 2]

    def set(self, x: int, y: int, color: Color) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            i = (y * self.width + x) * 3
            self.data[i : i + 3] = bytes(color)

    def fill_rect(self, x: int, y: int, w: int, h: int, color: Color) -> None:
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(self.width, x + w), min(self.height, y + h)
        if x1 <= x0 or y1 <= y0:
            return
        run = bytes(color) * (x1 - x0)
        for yy in range(y0, y1):
            i = (yy * self.width + x0) * 3
            self.data[i : i + len(run)] = run

    def blend_rect(self, x: int, y: int, w: int, h: int, color: Color, alpha: float) -> None:
        """Tint an area toward ``color`` (alpha 0..1)."""
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(self.width, x + w), min(self.height, y + h)
        if x1 <= x0 or y1 <= y0:
            return
        a = max(0.0, min(1.0, alpha))
        luts = [bytes(int(v * (1 - a) + c * a) for v in range(256)) for c in color]
        stride = (x1 - x0) * 3
        for yy in range(y0, y1):
            i = (yy * self.width + x0) * 3
            row = self.data[i : i + stride]
            for ch in range(3):
                row[ch::3] = row[ch::3].translate(luts[ch])
            self.data[i : i + stride] = row

    def scaled(self, factor: int) -> Canvas:
        """Nearest-neighbour upscale (chunky pixels)."""
        if factor == 1:
            return Canvas.from_rgb(self.width, self.height, bytes(self.data))
        out = Canvas(self.width * factor, self.height * factor)
        rows = []
        for y in range(self.height):
            row = self.data[y * self.width * 3 : (y + 1) * self.width * 3]
            wide = b"".join(bytes(row[i : i + 3]) * factor for i in range(0, len(row), 3))
            rows.append(wide * factor)
        out.data[:] = b"".join(rows)
        return out

    def blit(self, src: Canvas, x: int, y: int) -> None:
        sx0, tx0 = max(0, -x), max(0, x)
        n = min(src.width - sx0, self.width - tx0)
        if n <= 0:
            return
        for sy in range(src.height):
            ty = y + sy
            if not 0 <= ty < self.height:
                continue
            s = (sy * src.width + sx0) * 3
            t = (ty * self.width + tx0) * 3
            self.data[t : t + n * 3] = src.data[s : s + n * 3]

    def posterize(self, bits: int = 4) -> None:
        shift = 8 - bits
        top = (1 << bits) - 1
        lut = bytes(((v >> shift) * 255) // top for v in range(256))
        self.data[:] = self.data.translate(lut)

    def to_png(self) -> bytes:
        stride = self.width * 3
        raw = b"".join(
            b"\x00" + bytes(self.data[y * stride : (y + 1) * stride]) for y in range(self.height)
        )
        ihdr = struct.pack(">IIBBBBB", self.width, self.height, 8, 2, 0, 0, 0)
        body = _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", zlib.compress(raw, 9))
        return _SIG + body + _chunk(b"IEND", b"")


def _chunk(kind: bytes, body: bytes) -> bytes:
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))


def from_png(data: bytes) -> Canvas:
    """Read a PNG written by :meth:`Canvas.to_png` (RGB8, no interlace, filter-0 rows)."""
    if not isinstance(data, bytes | bytearray) or not bytes(data[:8]) == _SIG:
        raise ValueError("not a PNG")
    pos, idat, size = 8, [], None
    while pos + 8 <= len(data):
        (length,) = struct.unpack(">I", data[pos : pos + 4])
        kind = bytes(data[pos + 4 : pos + 8])
        body = bytes(data[pos + 8 : pos + 8 + length])
        pos += 12 + length
        if kind == b"IHDR":
            w, h, depth, ctype, _, _, inter = struct.unpack(">IIBBBBB", body)
            if (depth, ctype, inter) != (8, 2, 0) or not (0 < w <= MAX_SIDE and 0 < h <= MAX_SIDE):
                raise ValueError("unsupported PNG")
            size = (w, h)
        elif kind == b"IDAT":
            idat.append(body)
        elif kind == b"IEND":
            break
    if size is None:
        raise ValueError("PNG has no header")
    w, h = size
    stride = w * 3
    want = (stride + 1) * h
    raw = zlib.decompressobj().decompress(b"".join(idat), want + 1)
    if len(raw) != want:
        raise ValueError("PNG data size mismatch")
    out = bytearray()
    for y in range(h):
        row = raw[y * (stride + 1) : (y + 1) * (stride + 1)]
        if row[0] != 0:
            raise ValueError("unsupported PNG filter")
        out += row[1:]
    return Canvas.from_rgb(w, h, bytes(out))
