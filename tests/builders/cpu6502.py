"""A small but complete (official opcodes) 6502 + NES bus for tests of NROM-256 ROMs.

Enough NES to run the platformer engine headless: 2K RAM, 32K PRG, PPU registers with VRAM,
palette, OAM and OAM DMA, the $2002 vblank flag, controller 1 strobe/shift, and an APU write
log. ``frame()`` runs one frame of CPU time, then raises vblank and an NMI if enabled.
Not cycle exact; tests only look at state, not timing.
"""

from __future__ import annotations

CYCLES_PER_FRAME = 29780


class Nes:
    def __init__(self, rom: bytes) -> None:
        assert rom[:4] == b"NES\x1a" and rom[4] == 2
        self.prg = rom[16 : 16 + 0x8000]
        self.chr = rom[16 + 0x8000 :]
        self.ram = bytearray(0x800)
        self.vram = bytearray(0x4000)
        self.oam = bytearray(256)
        self.ppu_ctrl = self.ppu_mask = 0
        self.vblank = False
        self.latch = False
        self.vaddr = 0
        self.oam_addr = 0
        self.buttons = 0
        self.shift = 0
        self.strobe = False
        self.apu_writes: list[tuple[int, int]] = []
        self.frames = 0
        self.a = self.x = self.y = 0
        self.s = 0xFD
        self.p = 0x24
        self.pc = self.r16(0xFFFC)
        self.cycles = 0

    # ------------------------------------------------------------ bus
    def read(self, addr: int) -> int:
        addr &= 0xFFFF
        if addr < 0x2000:
            return self.ram[addr & 0x7FF]
        if addr < 0x4000:
            reg = addr & 7
            if reg == 2:
                v = 0x80 if self.vblank else 0
                self.vblank = False
                self.latch = False
                return v
            if reg == 7:
                v = self.vram[self.vaddr & 0x3FFF]
                self.vaddr += 32 if self.ppu_ctrl & 4 else 1
                return v
            return 0
        if addr == 0x4016:
            # Shifts out A, B, Select, Start, Up, Down, Left, Right (bit 7 first), then 1s.
            bit = (self.buttons if self.strobe else self.shift) >> 7 & 1
            if not self.strobe:
                self.shift = self.shift << 1 & 0xFF | 1
            return bit | 0x40
        if addr >= 0x8000:
            return self.prg[addr - 0x8000]
        return 0

    def _ppu_write(self, value: int) -> None:
        a = self.vaddr & 0x3FFF
        if a >= 0x3F00:
            a = 0x3F00 | a & 0x1F
            if a & 0x13 == 0x10:
                a &= ~0x10
        self.vram[a] = value
        self.vaddr += 32 if self.ppu_ctrl & 4 else 1

    def write(self, addr: int, value: int) -> None:
        addr &= 0xFFFF
        if addr < 0x2000:
            self.ram[addr & 0x7FF] = value
        elif addr < 0x4000:
            reg = addr & 7
            if reg == 0:
                self.ppu_ctrl = value
            elif reg == 1:
                self.ppu_mask = value
            elif reg == 3:
                self.oam_addr = value
            elif reg == 4:
                self.oam[self.oam_addr] = value
                self.oam_addr = self.oam_addr + 1 & 0xFF
            elif reg == 6:
                if not self.latch:
                    self.vaddr = (value & 0x3F) << 8 | self.vaddr & 0xFF
                else:
                    self.vaddr = self.vaddr & 0xFF00 | value
                self.latch = not self.latch
            elif reg == 7:
                self._ppu_write(value)
            elif reg == 5:
                self.latch = not self.latch
        elif addr == 0x4014:
            base = value << 8
            for i in range(256):
                self.oam[self.oam_addr + i & 0xFF] = self.read(base + i)
            self.cycles += 513
        elif addr == 0x4016:
            self.strobe = bool(value & 1)
            self.shift = self.buttons
        elif 0x4000 <= addr < 0x4018:
            self.apu_writes.append((addr, value))

    def r16(self, addr: int) -> int:
        return self.read(addr) | self.read(addr + 1) << 8

    # ------------------------------------------------------------ helpers
    def push(self, v: int) -> None:
        self.ram[0x100 | self.s] = v & 0xFF
        self.s = self.s - 1 & 0xFF

    def pull(self) -> int:
        self.s = self.s + 1 & 0xFF
        return self.ram[0x100 | self.s]

    def nz(self, v: int) -> int:
        v &= 0xFF
        self.p = self.p & 0x7D | (v & 0x80) | (0 if v else 2)
        return v

    def _fetch(self) -> int:
        v = self.read(self.pc)
        self.pc = self.pc + 1 & 0xFFFF
        return v

    def _fetch16(self) -> int:
        lo = self._fetch()
        return lo | self._fetch() << 8

    def _addr(self, mode: str) -> int:
        if mode == "zp":
            return self._fetch()
        if mode == "zpx":
            return self._fetch() + self.x & 0xFF
        if mode == "zpy":
            return self._fetch() + self.y & 0xFF
        if mode == "abs":
            return self._fetch16()
        if mode == "abx":
            return self._fetch16() + self.x & 0xFFFF
        if mode == "aby":
            return self._fetch16() + self.y & 0xFFFF
        if mode == "izx":
            z = self._fetch() + self.x & 0xFF
            return self.ram[z] | self.ram[z + 1 & 0xFF] << 8
        if mode == "izy":
            z = self._fetch()
            return (self.ram[z] | self.ram[z + 1 & 0xFF] << 8) + self.y & 0xFFFF
        raise AssertionError(mode)

    def _operand(self, mode: str) -> int:
        if mode == "imm":
            return self._fetch()
        if mode == "acc":
            return self.a
        return self.read(self._addr(mode))

    def _adc(self, v: int) -> None:
        c = self.p & 1
        r = self.a + v + c
        self.p = self.p & 0xBE | (1 if r > 0xFF else 0)
        if ~(self.a ^ v) & (self.a ^ r) & 0x80:
            self.p |= 0x40
        self.a = self.nz(r)

    def _cmp(self, reg: int, v: int) -> None:
        r = reg - v
        self.p = self.p & 0xFE | (1 if r >= 0 else 0)
        self.nz(r)

    def _branch(self, cond: bool) -> None:
        off = self._fetch()
        if cond:
            self.pc = self.pc + (off - 256 if off & 0x80 else off) & 0xFFFF

    def _rmw(self, mode: str, fn) -> None:
        if mode == "acc":
            self.a = fn(self.a)
        else:
            addr = self._addr(mode)
            self.write(addr, fn(self.read(addr)))

    def interrupt(self, vector: int, brk: bool = False) -> None:
        self.push(self.pc >> 8)
        self.push(self.pc)
        self.push(self.p | (0x30 if brk else 0x20))
        self.p |= 0x04
        self.pc = self.r16(vector)

    # ------------------------------------------------------------ execution
    def step(self) -> None:
        op = self._fetch()
        self.cycles += 3
        ins = _OPS.get(op)
        if ins is None:
            raise RuntimeError(f"illegal opcode ${op:02X} at ${self.pc - 1:04X}")
        name, mode = ins
        getattr(self, "_" + name.lower() + "_op")(mode)

    def frame(self) -> None:
        end = self.cycles + CYCLES_PER_FRAME
        while self.cycles < end:
            self.step()
        self.vblank = True
        self.frames += 1
        if self.ppu_ctrl & 0x80:
            self.interrupt(0xFFFA)

    def run(self, frames: int, buttons: int | None = None) -> None:
        if buttons is not None:
            self.buttons = buttons
        for _ in range(frames):
            self.frame()

    # loads/stores
    def _lda_op(self, m):
        self.a = self.nz(self._operand(m))

    def _ldx_op(self, m):
        self.x = self.nz(self._operand(m))

    def _ldy_op(self, m):
        self.y = self.nz(self._operand(m))

    def _sta_op(self, m):
        self.write(self._addr(m), self.a)

    def _stx_op(self, m):
        self.write(self._addr(m), self.x)

    def _sty_op(self, m):
        self.write(self._addr(m), self.y)

    def _tax_op(self, m):
        self.x = self.nz(self.a)

    def _tay_op(self, m):
        self.y = self.nz(self.a)

    def _txa_op(self, m):
        self.a = self.nz(self.x)

    def _tya_op(self, m):
        self.a = self.nz(self.y)

    def _tsx_op(self, m):
        self.x = self.nz(self.s)

    def _txs_op(self, m):
        self.s = self.x

    def _pha_op(self, m):
        self.push(self.a)

    def _php_op(self, m):
        self.push(self.p | 0x30)

    def _pla_op(self, m):
        self.a = self.nz(self.pull())

    def _plp_op(self, m):
        self.p = self.pull() & 0xEF | 0x20

    # logic/arith
    def _and_op(self, m):
        self.a = self.nz(self.a & self._operand(m))

    def _ora_op(self, m):
        self.a = self.nz(self.a | self._operand(m))

    def _eor_op(self, m):
        self.a = self.nz(self.a ^ self._operand(m))

    def _adc_op(self, m):
        self._adc(self._operand(m))

    def _sbc_op(self, m):
        self._adc(self._operand(m) ^ 0xFF)

    def _cmp_op(self, m):
        self._cmp(self.a, self._operand(m))

    def _cpx_op(self, m):
        self._cmp(self.x, self._operand(m))

    def _cpy_op(self, m):
        self._cmp(self.y, self._operand(m))

    def _bit_op(self, m):
        v = self._operand(m)
        self.p = self.p & 0x3D | v & 0xC0 | (0 if self.a & v else 2)

    def _inc_op(self, m):
        self._rmw(m, lambda v: self.nz(v + 1))

    def _dec_op(self, m):
        self._rmw(m, lambda v: self.nz(v - 1))

    def _inx_op(self, m):
        self.x = self.nz(self.x + 1)

    def _iny_op(self, m):
        self.y = self.nz(self.y + 1)

    def _dex_op(self, m):
        self.x = self.nz(self.x - 1)

    def _dey_op(self, m):
        self.y = self.nz(self.y - 1)

    def _asl_op(self, m):
        def f(v):
            self.p = self.p & 0xFE | v >> 7
            return self.nz(v << 1)

        self._rmw(m, f)

    def _lsr_op(self, m):
        def f(v):
            self.p = self.p & 0xFE | v & 1
            return self.nz(v >> 1)

        self._rmw(m, f)

    def _rol_op(self, m):
        def f(v):
            c = self.p & 1
            self.p = self.p & 0xFE | v >> 7
            return self.nz(v << 1 | c)

        self._rmw(m, f)

    def _ror_op(self, m):
        def f(v):
            c = self.p & 1
            self.p = self.p & 0xFE | v & 1
            return self.nz(v >> 1 | c << 7)

        self._rmw(m, f)

    # flow
    def _jmp_op(self, m):
        a = self._fetch16()
        if m == "ind":
            a = self.read(a) | self.read(a & 0xFF00 | a + 1 & 0xFF) << 8
        self.pc = a

    def _jsr_op(self, m):
        a = self._fetch16()
        ret = self.pc - 1 & 0xFFFF
        self.push(ret >> 8)
        self.push(ret)
        self.pc = a

    def _rts_op(self, m):
        lo = self.pull()
        self.pc = (lo | self.pull() << 8) + 1 & 0xFFFF

    def _rti_op(self, m):
        self.p = self.pull() & 0xEF | 0x20
        lo = self.pull()
        self.pc = lo | self.pull() << 8

    def _brk_op(self, m):
        self.pc = self.pc + 1 & 0xFFFF
        self.interrupt(0xFFFE, brk=True)

    def _bpl_op(self, m):
        self._branch(not self.p & 0x80)

    def _bmi_op(self, m):
        self._branch(bool(self.p & 0x80))

    def _bvc_op(self, m):
        self._branch(not self.p & 0x40)

    def _bvs_op(self, m):
        self._branch(bool(self.p & 0x40))

    def _bcc_op(self, m):
        self._branch(not self.p & 1)

    def _bcs_op(self, m):
        self._branch(bool(self.p & 1))

    def _bne_op(self, m):
        self._branch(not self.p & 2)

    def _beq_op(self, m):
        self._branch(bool(self.p & 2))

    def _clc_op(self, m):
        self.p &= 0xFE

    def _sec_op(self, m):
        self.p |= 1

    def _cli_op(self, m):
        self.p &= 0xFB

    def _sei_op(self, m):
        self.p |= 4

    def _clv_op(self, m):
        self.p &= 0xBF

    def _cld_op(self, m):
        self.p &= 0xF7

    def _sed_op(self, m):
        self.p |= 8

    def _nop_op(self, m):
        pass


def _table() -> dict[int, tuple[str, str]]:
    groups = {
        "ORA": (0x00,),
        "AND": (0x20,),
        "EOR": (0x40,),
        "ADC": (0x60,),
        "STA": (0x80,),
        "LDA": (0xA0,),
        "CMP": (0xC0,),
        "SBC": (0xE0,),
    }
    ops: dict[int, tuple[str, str]] = {}
    for name, (base,) in groups.items():
        for off, mode in (
            (1, "izx"),
            (5, "zp"),
            (9, "imm"),
            (0xD, "abs"),
            (0x11, "izy"),
            (0x15, "zpx"),
            (0x19, "aby"),
            (0x1D, "abx"),
        ):
            if name == "STA" and mode == "imm":
                continue
            ops[base + off] = (name, mode)
    for name, base in (("ASL", 0x00), ("ROL", 0x20), ("LSR", 0x40), ("ROR", 0x60)):
        for off, mode in ((6, "zp"), (0xA, "acc"), (0xE, "abs"), (0x16, "zpx"), (0x1E, "abx")):
            ops[base + off] = (name, mode)
    for name, base in (("DEC", 0xC0), ("INC", 0xE0)):
        for off, mode in ((6, "zp"), (0xE, "abs"), (0x16, "zpx"), (0x1E, "abx")):
            ops[base + off] = (name, mode)
    more = {
        0xA2: ("LDX", "imm"),
        0xA6: ("LDX", "zp"),
        0xAE: ("LDX", "abs"),
        0xB6: ("LDX", "zpy"),
        0xBE: ("LDX", "aby"),
        0xA0: ("LDY", "imm"),
        0xA4: ("LDY", "zp"),
        0xAC: ("LDY", "abs"),
        0xB4: ("LDY", "zpx"),
        0xBC: ("LDY", "abx"),
        0x86: ("STX", "zp"),
        0x8E: ("STX", "abs"),
        0x96: ("STX", "zpy"),
        0x84: ("STY", "zp"),
        0x8C: ("STY", "abs"),
        0x94: ("STY", "zpx"),
        0xE0: ("CPX", "imm"),
        0xE4: ("CPX", "zp"),
        0xEC: ("CPX", "abs"),
        0xC0: ("CPY", "imm"),
        0xC4: ("CPY", "zp"),
        0xCC: ("CPY", "abs"),
        0x24: ("BIT", "zp"),
        0x2C: ("BIT", "abs"),
        0x4C: ("JMP", "abs"),
        0x6C: ("JMP", "ind"),
        0x20: ("JSR", "abs"),
        0x60: ("RTS", ""),
        0x40: ("RTI", ""),
        0x00: ("BRK", ""),
        0x10: ("BPL", ""),
        0x30: ("BMI", ""),
        0x50: ("BVC", ""),
        0x70: ("BVS", ""),
        0x90: ("BCC", ""),
        0xB0: ("BCS", ""),
        0xD0: ("BNE", ""),
        0xF0: ("BEQ", ""),
        0xAA: ("TAX", ""),
        0xA8: ("TAY", ""),
        0x8A: ("TXA", ""),
        0x98: ("TYA", ""),
        0xBA: ("TSX", ""),
        0x9A: ("TXS", ""),
        0x48: ("PHA", ""),
        0x08: ("PHP", ""),
        0x68: ("PLA", ""),
        0x28: ("PLP", ""),
        0xE8: ("INX", ""),
        0xC8: ("INY", ""),
        0xCA: ("DEX", ""),
        0x88: ("DEY", ""),
        0x18: ("CLC", ""),
        0x38: ("SEC", ""),
        0x58: ("CLI", ""),
        0x78: ("SEI", ""),
        0xB8: ("CLV", ""),
        0xD8: ("CLD", ""),
        0xF8: ("SED", ""),
        0xEA: ("NOP", ""),
    }
    ops.update(more)
    return ops


_OPS = _table()
