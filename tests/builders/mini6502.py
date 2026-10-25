"""Tiny 6502 + PPU-register model, just enough to boot RetroBake's NROM "hello" engine.

Not an emulator: it runs the reset code, records what reaches PPU memory and stops when the
program settles into its idle loop. Real emulator boots are qa's smoke test.
"""

from __future__ import annotations


class Unsupported(Exception):
    pass


class Machine:
    def __init__(self, rom: bytes) -> None:
        self.prg = rom[16 : 16 + 16384]
        self.ram = bytearray(0x800)
        self.vram = bytearray(0x4000)
        self.a = self.x = self.y = 0
        self.sp = 0xFD
        self.n = self.z = self.c = False
        self.vblank_toggle = False
        self.latch_hi = True
        self.vaddr = 0
        self.ppuctrl = self.ppumask = 0
        self.buttons = 0  # bit7 A, 6 B, 5 Select, 4 Start, 3 Up, 2 Down, 1 Left, 0 Right
        self.shift = 0
        self.frames = 0
        self.pc = self.read16(0xFFFC)

    # -- memory
    def read(self, addr: int) -> int:
        addr &= 0xFFFF
        if addr < 0x2000:
            return self.ram[addr & 0x7FF]
        if addr == 0x2002:
            self.vblank_toggle = not self.vblank_toggle
            self.latch_hi = True
            return 0x80 if self.vblank_toggle else 0x00
        if addr == 0x4016:  # serial pad: A first, 1s after the 8th read
            bit = (self.shift >> 7) & 1
            self.shift = ((self.shift << 1) | 1) & 0xFF
            return bit
        if addr >= 0xC000:
            return self.prg[addr - 0xC000]
        return 0

    def read16(self, addr: int) -> int:
        return self.read(addr) | self.read(addr + 1) << 8

    def write(self, addr: int, val: int) -> None:
        addr &= 0xFFFF
        if addr < 0x2000:
            self.ram[addr & 0x7FF] = val
        elif addr == 0x2000:
            self.ppuctrl = val
        elif addr == 0x2001:
            self.ppumask = val
        elif addr == 0x2006:
            if self.latch_hi:
                self.vaddr = (val << 8) & 0x3F00
            else:
                self.vaddr = (self.vaddr & 0xFF00) | val
            self.latch_hi = not self.latch_hi
        elif addr == 0x2007:
            self.vram[self.vaddr & 0x3FFF] = val
            self.vaddr += 32 if self.ppuctrl & 4 else 1
        elif addr == 0x2005:
            self.latch_hi = not self.latch_hi
        elif addr == 0x4016 and val & 1:
            self.shift = self.buttons

    def _push(self, v: int) -> None:
        self.ram[0x100 + self.sp] = v & 0xFF
        self.sp = (self.sp - 1) & 0xFF

    def _pull(self) -> int:
        self.sp = (self.sp + 1) & 0xFF
        return self.ram[0x100 + self.sp]

    def nmi(self) -> None:
        self._push(self.pc >> 8)
        self._push(self.pc)
        self._push(0x20 | self.n << 7 | self.z << 1 | int(self.c))
        self.pc = self.read16(0xFFFA)
        self.frames += 1

    # -- helpers
    def _nz(self, v: int) -> int:
        v &= 0xFF
        self.n, self.z = bool(v & 0x80), v == 0
        return v

    def _imm(self) -> int:
        v = self.read(self.pc)
        self.pc += 1
        return v

    def _abs(self) -> int:
        v = self.read16(self.pc)
        self.pc += 2
        return v

    def _branch(self, cond: bool) -> None:
        off = self._imm()
        if cond:
            self.pc = (self.pc + (off - 256 if off & 0x80 else off)) & 0xFFFF

    def step(self) -> None:
        op = self._imm()
        if op in (0x78, 0xD8, 0xEA):  # SEI CLD NOP
            pass
        elif op == 0xA9:
            self.a = self._nz(self._imm())
        elif op == 0xA2:
            self.x = self._nz(self._imm())
        elif op == 0xA0:
            self.y = self._nz(self._imm())
        elif op == 0xAD:
            self.a = self._nz(self.read(self._abs()))
        elif op == 0xBD:
            self.a = self._nz(self.read(self._abs() + self.x))
        elif op == 0xB1:
            zp = self._imm()
            base = self.read(zp) | self.read((zp + 1) & 0xFF) << 8
            self.a = self._nz(self.read(base + self.y))
        elif op == 0x8D:
            self.write(self._abs(), self.a)
        elif op == 0x8E:
            self.write(self._abs(), self.x)
        elif op == 0x8C:
            self.write(self._abs(), self.y)
        elif op == 0x85:
            self.write(self._imm(), self.a)
        elif op == 0x95:
            self.write((self._imm() + self.x) & 0xFF, self.a)
        elif op == 0x9D:
            self.write(self._abs() + self.x, self.a)
        elif op == 0xA5:
            self.a = self._nz(self.read(self._imm()))
        elif op == 0xC5 or op == 0xC9:
            v = self.read(self._imm()) if op == 0xC5 else self._imm()
            self.c = self.a >= v
            self._nz(self.a - v)
        elif op == 0x29:
            self.a = self._nz(self.a & self._imm())
        elif op == 0x4A:
            self.c = bool(self.a & 1)
            self.a = self._nz(self.a >> 1)
        elif op == 0x26:
            zp = self._imm()
            v = (self.read(zp) << 1) | int(self.c)
            self.c = v > 0xFF
            self.write(zp, self._nz(v))
        elif op == 0x48:
            self._push(self.a)
        elif op == 0x68:
            self.a = self._nz(self._pull())
        elif op == 0x40:  # RTI
            p = self._pull()
            self.n, self.z, self.c = bool(p & 0x80), bool(p & 2), bool(p & 1)
            self.pc = self._pull() | self._pull() << 8
        elif op == 0x2C:
            v = self.read(self._abs())
            self.n, self.z = bool(v & 0x80), (v & self.a) == 0
        elif op in (0x9A, 0x8A, 0xAA, 0x98, 0xA8):  # TXS TXA TAX TYA TAY
            if op == 0x9A:
                self.sp = self.x
            elif op == 0x8A:
                self.a = self._nz(self.x)
            elif op == 0xAA:
                self.x = self._nz(self.a)
            elif op == 0x98:
                self.a = self._nz(self.y)
            else:
                self.y = self._nz(self.a)
        elif op == 0xE8:
            self.x = self._nz(self.x + 1)
        elif op == 0xCA:
            self.x = self._nz(self.x - 1)
        elif op == 0xC8:
            self.y = self._nz(self.y + 1)
        elif op == 0x88:
            self.y = self._nz(self.y - 1)
        elif op == 0xE6:
            zp = self._imm()
            self.write(zp, self._nz(self.read(zp) + 1))
        elif op == 0xE0:
            v = self._imm()
            self.c = self.x >= v
            self._nz(self.x - v)
        elif op == 0x18:
            self.c = False
        elif op == 0x65:
            s = self.a + self.read(self._imm()) + int(self.c)
            self.c = s > 0xFF
            self.a = self._nz(s)
        elif op == 0x10:
            self._branch(not self.n)
        elif op == 0xD0:
            self._branch(not self.z)
        elif op == 0xF0:
            self._branch(self.z)
        elif op == 0x90:
            self._branch(not self.c)
        elif op == 0x4C:
            self.pc = self._abs()
        else:
            raise Unsupported(f"opcode ${op:02X} at ${self.pc - 1:04X}")

    def run_frames(self, frames: int, steps_per_frame: int = 3000, max_boot: int = 500_000):
        """Boot (until NMI is switched on), then run ``frames`` NMI-driven frames."""
        for _ in range(max_boot):
            if self.ppuctrl & 0x80:
                break
            self.step()
        else:
            raise TimeoutError("program never switched on its frame interrupt")
        for _ in range(frames):
            self.nmi()
            for _ in range(steps_per_frame):
                self.step()

    def ram_sig(self) -> bytes:
        return bytes(self.ram[0x7FC:0x800])
