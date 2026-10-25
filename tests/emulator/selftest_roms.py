"""Generate two tiny reference ROMs that follow the boot-signature contract.

They prove the harness and the CI cores work before the real engines exist, and they
are the "known good" baseline if an engine ROM later fails. Both are original code
written here (no third-party assets): a solid-colour screen, the "RB" signature in RAM
with state 1 (title), and state 2 (gameplay) once Start is pressed.
"""

from __future__ import annotations

from pathlib import Path

SIG_STATE_TITLE = 1
SIG_STATE_GAMEPLAY = 2


def nes_rom() -> bytes:
    """NROM-128 (mapper 0): 16 KB PRG at $C000 (mirrored at $8000) + 8 KB blank CHR."""
    org = 0xC000
    c = bytearray()
    # reset: sei, cld, disable APU frame IRQ, stack, PPU off, DMC off
    c += bytes([0x78, 0xD8, 0xA2, 0x40, 0x8E, 0x17, 0x40, 0xA2, 0xFF, 0x9A, 0xE8])
    c += bytes([0x8E, 0x00, 0x20, 0x8E, 0x01, 0x20, 0x8E, 0x10, 0x40])
    for _ in range(2):  # wait two vblanks for the PPU to warm up: bit $2002 / bpl
        c += bytes([0x2C, 0x02, 0x20, 0x10, 0xFB])
    # backdrop colour $3F00 = $21 (light blue), then reset the PPU address
    c += bytes([0xA9, 0x3F, 0x8D, 0x06, 0x20, 0xA9, 0x00, 0x8D, 0x06, 0x20])
    c += bytes([0xA9, 0x21, 0x8D, 0x07, 0x20, 0xA9, 0x00, 0x8D, 0x06, 0x20, 0x8D, 0x06, 0x20])
    for addr, val in ((0x07FC, 0x52), (0x07FD, 0x42), (0x07FE, 1), (0x07FF, SIG_STATE_TITLE)):
        c += bytes([0xA9, val, 0x8D, addr & 0xFF, addr >> 8])  # lda #val / sta addr
    c += bytes([0xA9, 0x08, 0x8D, 0x01, 0x20])  # show background
    main = org + len(c)
    c += bytes([0xA9, 0x01, 0x8D, 0x16, 0x40, 0xA9, 0x00, 0x8D, 0x16, 0x40])  # strobe pad 1
    c += bytes([0xAD, 0x16, 0x40]) * 3  # A, B, Select
    c += bytes([0xAD, 0x16, 0x40, 0x29, 0x01, 0xF0, 0x00])  # Start? beq main
    c[-1] = (main - (org + len(c))) & 0xFF
    c += bytes([0xA9, SIG_STATE_GAMEPLAY, 0x8D, 0xFF, 0x07, 0x4C, main & 0xFF, main >> 8])
    rti = org + len(c)
    c += bytes([0x40])
    prg = bytearray(0x4000)
    prg[: len(c)] = c
    prg[0x3FFA:0x4000] = bytes([rti & 0xFF, rti >> 8, org & 0xFF, org >> 8, rti & 0xFF, rti >> 8])
    header = b"NES\x1a" + bytes([1, 1, 0, 0]) + bytes(8)
    return header + bytes(prg) + bytes(0x2000)


def snes_rom() -> bytes:
    """32 KB LoROM, code at $00:8000, 8-bit native mode, valid header checksum."""
    c = bytearray()
    c += bytes([0x78, 0x18, 0xFB])  # sei, clc, xce (native mode, 8-bit A/X)
    c += bytes([0xA9, 0x80, 0x8D, 0x00, 0x21])  # force blank
    c += bytes([0x9C, 0x00, 0x42, 0x9C, 0x21, 0x21])  # NMI off, CGRAM address 0
    c += bytes([0xA9, 0x1F, 0x8D, 0x22, 0x21, 0x9C, 0x22, 0x21])  # colour 0 = red
    for addr, val in ((0x1FFC, 0x52), (0x1FFD, 0x42), (0x1FFE, 1), (0x1FFF, SIG_STATE_TITLE)):
        c += bytes([0xA9, val, 0x8D, addr & 0xFF, addr >> 8])  # WRAM $7E:1FFC.. via bank 0
    c += bytes([0xA9, 0x0F, 0x8D, 0x00, 0x21])  # screen on, full brightness
    c += bytes([0xA9, 0x01, 0x8D, 0x00, 0x42])  # joypad auto-read on
    main = 0x8000 + len(c)
    c += bytes([0xAD, 0x12, 0x42, 0x10, 0xFB])  # wait for vblank (bit 7 of $4212)
    c += bytes([0xAD, 0x12, 0x42, 0x29, 0x01, 0xD0, 0xF9])  # wait until auto-read done
    c += bytes([0xAD, 0x19, 0x42, 0x29, 0x10, 0xF0, 0x00])  # JOY1H & Start? beq main
    c[-1] = (main - (0x8000 + len(c))) & 0xFF
    c += bytes([0xA9, SIG_STATE_GAMEPLAY, 0x8D, 0xFF, 0x1F, 0x4C, main & 0xFF, main >> 8])
    rti = 0x8000 + len(c)
    c += bytes([0x40])

    rom = bytearray(0x8000)
    rom[: len(c)] = c
    rom[0x7FC0:0x7FD5] = b"RETROBAKE SELFTEST".ljust(21)
    rom[0x7FD5] = 0x20  # LoROM
    rom[0x7FD6] = 0x00  # ROM only
    rom[0x7FD7] = 0x05  # 32 KB
    rom[0x7FD8] = 0x00  # no SRAM
    rom[0x7FD9] = 0x01  # region: North America
    rom[0x7FDA] = 0x00
    rom[0x7FDB] = 0x00
    lo, hi = rti & 0xFF, rti >> 8
    for vec in range(0x7FE4, 0x7FF0, 2):  # native COP/BRK/ABORT/NMI/-/IRQ
        rom[vec : vec + 2] = bytes([lo, hi])
    for vec in (0x7FF4, 0x7FF8, 0x7FFA, 0x7FFE):  # emulation COP/ABORT/NMI/IRQ
        rom[vec : vec + 2] = bytes([lo, hi])
    rom[0x7FFC:0x7FFE] = bytes([0x00, 0x80])  # emulation RESET -> $8000
    rom[0x7FDC:0x7FE0] = bytes([0xFF, 0xFF, 0x00, 0x00])
    csum = sum(rom) & 0xFFFF
    comp = csum ^ 0xFFFF
    rom[0x7FDC:0x7FE0] = bytes([comp & 0xFF, comp >> 8, csum & 0xFF, csum >> 8])
    return bytes(rom)


def write_selftest_roms(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    nes = out_dir / "selftest.nes"
    sfc = out_dir / "selftest.sfc"
    nes.write_bytes(nes_rom())
    sfc.write_bytes(snes_rom())
    return [nes, sfc]
