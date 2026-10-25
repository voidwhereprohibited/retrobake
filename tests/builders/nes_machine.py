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
