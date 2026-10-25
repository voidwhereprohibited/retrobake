"""Static checks on the reference ROMs and the smoke-test verdict logic (no emulator needed)."""

from __future__ import annotations

from run_smoke import check
from selftest_roms import nes_rom, snes_rom


def test_nes_rom_layout():
    rom = nes_rom()
    assert rom[:4] == b"NES\x1a" and rom[4] == 1 and rom[5] == 1
    assert len(rom) == 16 + 0x4000 + 0x2000
    prg = rom[16 : 16 + 0x4000]
    reset = prg[0x3FFC] | prg[0x3FFD] << 8
    assert reset == 0xC000 and prg[0] == 0x78  # sei
    for vec in (0x3FFA, 0x3FFE):
        target = (prg[vec] | prg[vec + 1] << 8) - 0xC000
        assert prg[target] == 0x40  # rti


def test_snes_rom_header_checksum():
    rom = snes_rom()
    assert len(rom) == 0x8000 and rom[0x7FD5] == 0x20
    comp = rom[0x7FDC] | rom[0x7FDD] << 8
    csum = rom[0x7FDE] | rom[0x7FDF] << 8
    assert comp ^ csum == 0xFFFF
    assert sum(rom) & 0xFFFF == csum
    assert rom[0x7FFC:0x7FFE] == b"\x00\x80"


def _good() -> dict:
    return {
        "loaded": True,
        "frames_drawn": 370,
        "frame": {"width": 256, "height": 240, "colors": 1, "nonblack": 1.0},
        "sig_boot": [0x52, 0x42, 1, 1],
        "sig_after_start": [0x52, 0x42, 1, 2],
    }


def test_check_passes_good_boot():
    assert check(_good()) == []


def test_check_flags_each_failure():
    assert check({"error": "hung"}) == ["hung"]
    assert check({"loaded": False}) == ["core refused to load the ROM"]
    for key, value, word in (
        ("frame", {"width": 256, "height": 240, "nonblack": 0}, "black"),
        ("sig_boot", [0, 0, 0, 0], "signature"),
        ("sig_after_start", [0x52, 0x42, 1, 1], "gameplay"),
        ("sig_after_start", [0x52, 0x42, 1, 0xEE], "fatal"),
        ("frames_drawn", 3, "frames"),
    ):
        res = _good()
        res[key] = value
        assert any(word in p for p in check(res)), key
