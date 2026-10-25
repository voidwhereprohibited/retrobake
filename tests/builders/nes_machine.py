"""Headless NES test bench for RetroBake engines: py65's full 6502 + a PPU-register model.

Not an emulator: no pixels are drawn. It runs the real ROM code at NTSC frame timing, fires
NMIs, models the controller, OAM DMA and PPU memory writes, so tests can check what the game
put on screen and in RAM. Real-emulator boots are qa's smoke test (tests/emulator).
"""

from __future__ import annotations

import re
from pathlib import Path

from py65.devices.mpu6502 import MPU

CYCLES_PER_FRAME = 29781


class Bus:
    def __init__(self, machine: Machine) -> None:
        self.m = machine

    def __getitem__(self, addr: int) -> int:
        m = self.m
        if addr < 0x2000:
            return m.ram[addr & 0x7FF]
        if addr >= 0x8000:
            return m.prg[(addr - 0x8000) % len(m.prg)]
        if addr & 0xE007 == 0x2002:
            v = 0x80 if m.vblank else 0
            m.vblank = False
            m.latch_hi = True
            return v
        if addr == 0x4016:
            bit = (m.shift >> 7) & 1
            m.shift = ((m.shift << 1) | 1) & 0xFF
            return bit
        return 0

    def __setitem__(self, addr: int, val: int) -> None:
        m = self.m
        val &= 0xFF
        if addr < 0x2000:
            m.ram[addr & 0x7FF] = val
            return
        if 0x2000 <= addr < 0x4000:
            reg = addr & 7
            if reg == 0:
                m.ppuctrl = val
            elif reg == 1:
                m.ppumask = val
            elif reg == 5:
                if m.latch_hi:
                    m.scroll_x = val
                m.latch_hi = not m.latch_hi
            elif reg == 6:
                if m.latch_hi:
                    m.vaddr = (val << 8) & 0x3F00
                else:
                    m.vaddr = (m.vaddr & 0xFF00) | val
                m.latch_hi = not m.latch_hi
            elif reg == 7:
                m.vram[m.vaddr & 0x3FFF] = val
                m.vaddr = (m.vaddr + (32 if m.ppuctrl & 4 else 1)) & 0x3FFF
            return
        if addr == 0x4014:
            base = val << 8
            m.oam[:] = bytes(self[base + i] for i in range(256))
        elif addr == 0x4016 and val & 1:
            m.shift = m.buttons


class Machine:
    A, B, SELECT, START, UP, DOWN, LEFT, RIGHT = 0x80, 0x40, 0x20, 0x10, 8, 4, 2, 1

    def __init__(self, rom: bytes) -> None:
        banks = rom[4]
        self.prg = rom[16 : 16 + banks * 16384]
        self.ram = bytearray(0x800)
        self.vram = bytearray(0x4000)
        self.oam = bytearray(256)
        self.ppuctrl = self.ppumask = self.scroll_x = 0
        self.vblank = False
        self.latch_hi = True
        self.vaddr = 0
        self.buttons = 0
        self.shift = 0
        self.frames = 0
        self.cpu = MPU(memory=Bus(self))
        self.cpu.pc = self.prg[-4] | self.prg[-3] << 8

    # -- running
    def _nmi(self) -> None:
        self.cpu.nmi()

    def run_frames(self, frames: int) -> None:
        for _ in range(frames):
            end = self.cpu.processorCycles + CYCLES_PER_FRAME
            while self.cpu.processorCycles < end:
                self.cpu.step()
            self.frames += 1
            self.vblank = True
            if self.ppuctrl & 0x80:
                self._nmi()

    def hold(self, buttons: int, frames: int) -> None:
        self.buttons = buttons
        self.run_frames(frames)
        self.buttons = 0

    def tap(self, buttons: int, frames: int = 2) -> None:
        self.hold(buttons, frames)
        self.run_frames(2)

    # -- looking
    def ram_sig(self) -> bytes:
        return bytes(self.ram[0x7FC:0x800])

    def nametable_text(self, row: int, nt: int = 0) -> bytes:
        base = 0x2000 + nt * 0x400 + row * 32
        return bytes(self.vram[base : base + 32])

    def sprites(self) -> list[tuple[int, int, int, int]]:
        """Visible sprites as (y, tile, attr, x)."""
        o = self.oam
        return [tuple(o[i : i + 4]) for i in range(0, 256, 4) if o[i] < 0xEF]


def zp_symbols(main_s: Path) -> dict[str, int]:
    """Zero-page addresses from a template's ``.segment "ZEROPAGE"`` block of ``name: .res n``."""
    text = main_s.read_text()
    block = text.split('.segment "ZEROPAGE"', 1)[1].split(".segment", 1)[0]
    addr, out = 0, {}
    for name, size in re.findall(r"^(\w+):\s+\.res\s+(\d+)", block, re.M):
        out[name] = addr
        addr += int(size)
    return out


# ---------------------------------------------------------------- screenshots (review aid)

_NES_RGB = bytes.fromhex(
    "757575271B8F0000AB47009F8F0077AB0013A700007F0B00432F00004700005100003F171B3F5F000000000000000000"
    "BCBCBC0073EF233BEF8300F3BF00BFE7005BDB2B00CB4F0F8B7300009700"
    "00AB0000933B00838B000000000000000000"
    "FFFFFF3FBFFF5F97FFA78BFDF77BFFFF77B7FF7763FF9B3BF3BF3F83D3134FDF4B58F89800EBDB757575000000000000"
    "FFFFFFABE7FFC7D7FFD7CBFFFFC7FFFFC7DBFFBFB3FFDBABFFE7A3E3FFA3ABF3BFB3FFCF9FFFF3BCBCBC000000000000"
)


def _pixel(chr_rom: bytes, table: int, tile: int, x: int, y: int) -> int:
    base = table * 4096 + tile * 16
    lo = chr_rom[base + y] >> (7 - x) & 1
    hi = chr_rom[base + 8 + y] >> (7 - x) & 1
    return lo | hi << 1


def screenshot(m: Machine, chr_rom: bytes, path: Path) -> None:
    """Render the current background + sprites (approximate) to a PNG."""
    import struct
    import zlib

    pal = m.vram[0x3F00:0x3F20]
    bg_table = (m.ppuctrl >> 4) & 1
    spr_table = (m.ppuctrl >> 3) & 1
    sx = m.scroll_x + (m.ppuctrl & 1) * 256
    img = [[pal[0]] * 256 for _ in range(240)]
    if m.ppumask & 0x08:
        for y in range(240):
            row = img[y]
            for x in range(256):
                wx = (sx + x) % 512
                nt = 0x2000 + (wx // 256) * 0x400
                cx, cy = (wx % 256) // 8, y // 8
                tile = m.vram[nt + cy * 32 + cx]
                attr = m.vram[nt + 0x3C0 + (cy // 4) * 8 + cx // 4]
                p = attr >> (((cy // 2) % 2) * 4 + ((cx // 2) % 2) * 2) & 3
                c = _pixel(chr_rom, bg_table, tile, wx % 8, y % 8)
                if c:
                    row[x] = pal[p * 4 + c]
    if m.ppumask & 0x10:
        for i in range(252, -4, -4):
            sy, tile, attr, sxp = m.oam[i : i + 4]
            if sy >= 0xEF:
                continue
            for py in range(8):
                for px in range(8):
                    tx = 7 - px if attr & 0x40 else px
                    ty = 7 - py if attr & 0x80 else py
                    c = _pixel(chr_rom, spr_table, tile, tx, ty)
                    X, Y = sxp + px, sy + 1 + py
                    if c and X < 256 and Y < 240:
                        img[Y][X] = pal[16 + (attr & 3) * 4 + c]
    raw = b"".join(
        b"\x00" + b"".join(_NES_RGB[(v & 0x3F) * 3 : (v & 0x3F) * 3 + 3] for v in row)
        for row in img
    )

    def chunk(kind: bytes, data: bytes) -> bytes:
        crc = struct.pack(">I", zlib.crc32(kind + data))
        return struct.pack(">I", len(data)) + kind + data + crc

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 256, 240, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)
