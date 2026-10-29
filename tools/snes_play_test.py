"""SNES platformer play test: bake sample games, boot them on Snes9x, press buttons, check.

CI entry point for the snes-engine (exits nonzero on any failure). Never run on Roger's PC.

For every sample spec (covering every combat style and extra) it bakes a ROM, then boots it in a
child process with qa's libretro harness (tests/emulator/libretro_harness.py) and checks that:
  1. the title screen publishes the boot signature "RB" v1 state 1,
  2. Start reaches gameplay (state 2),
  3. holding Right moves the hero right, and B makes the hero jump (debug probe, see
     docs/snes-builder.md),
  4. 1500 frames of scripted play never report a fatal error, the game never stalls (its frame
     counter keeps pace with the emulator) and the signature stays intact.
A PNG screenshot of each run is saved next to the ROMs for the README / bug reports.

    python tools/snes_play_test.py --cores tests/emulator/.cores --out baked/play
"""

from __future__ import annotations

import argparse
import json
import struct
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests" / "emulator"))

PROBE = 0x1FF0  # WRAM debug probe written by the platformer engine every frame
SIG = 0x1FFC
BUTTONS = {
    "B": 0,
    "Y": 1,
    "SELECT": 2,
    "START": 3,
    "UP": 4,
    "DOWN": 5,
    "LEFT": 6,
    "RIGHT": 7,
    "A": 8,
}
TIMEOUT_S = 180

SAMPLES = {
    "stomp-lives": {"combat": "stomp", "extras": ["lives", "collectibles", "bosses"]},
    "melee-dungeons": {
        "combat": "melee",
        "progression": "dungeons_items",
        "extras": ["hearts", "keys_doors", "bosses", "collectibles", "score", "shop"],
        "setting": "castle",
        "hero": "knight",
    },
    "shooter-timer": {
        "combat": "projectile",
        "extras": ["lives", "collectibles", "score", "timer"],
        "setting": "ice",
        "hero": "robot",
        "mood": "icy",
    },
    "peaceful-openmap": {
        "combat": "none",
        "progression": "open_map",
        "extras": ["hearts", "collectibles"],
        "setting": "desert",
        "hero": "animal",
        "mood": "warm",
    },
}

# scripted play: (frames, buttons) repeated
SCRIPT = [
    (20, ("RIGHT",)),
    (14, ("RIGHT", "B")),
    (10, ("RIGHT", "Y")),
    (6, ()),
    (18, ("RIGHT", "B", "Y")),
    (8, ("LEFT",)),
    (12, ("RIGHT", "A")),
]


def make_spec(title: str, opts: dict) -> dict:
    from retrobake import spec as gs

    spec, _ = gs.new_spec("snes", ["platformer"], "a sample game", title, seed=7)
    mods, world = spec["modules"], spec["world"]
    for key in ("combat", "extras", "progression"):
        if key in opts:
            mods[key] = list(opts[key]) if key == "extras" else opts[key]
    if mods["progression"] == "dungeons_items":
        world.pop("levels", None)
        world["dungeons"] = 2
    if mods["progression"] == "open_map":
        world.pop("levels", None)
        world["map_size"] = "small"
    if "setting" in opts:
        world["setting"] = opts["setting"]
    if "hero" in opts:
        spec["hero"]["archetype"] = opts["hero"]
    if "mood" in opts:
        spec["style"]["palette_mood"] = opts["mood"]
    return spec


def bake_samples(out: Path) -> list[Path]:
    from retrobake import spec as gs
    from retrobake.builders import snes

    out.mkdir(parents=True, exist_ok=True)
    roms = []
    for name, opts in SAMPLES.items():
        spec = make_spec("Play Test", opts)
        errors = gs.validate(spec)
        if errors:
            raise SystemExit(f"sample {name} is not a valid spec: {errors}")
        rom = snes.bake(spec).rom
        path = out / f"play-{name}.sfc"
        path.write_bytes(rom)
        roms.append(path)
        print(f"baked {path.name} ({len(rom)} bytes)")
    return roms


def write_png(path: Path, frame: tuple[bytes, int, int, int], fmt: int) -> None:
    buf, width, height, pitch = frame
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        line = memoryview(buf[y * pitch : y * pitch + width * (4 if fmt == 1 else 2)])
        px = line.cast("I" if fmt == 1 else "H")
        for v in px:
            if fmt == 1:
                rows += bytes(((v >> 16) & 255, (v >> 8) & 255, v & 255))
            elif fmt == 2:
                rows += bytes(((v >> 11) << 3, ((v >> 5) & 63) << 2, (v & 31) << 3))
            else:
                rows += bytes((((v >> 10) & 31) << 3, ((v >> 5) & 31) << 3, (v & 31) << 3))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(bytes(rows)))
    path.write_bytes(png + chunk(b"IEND", b""))


def play(core: Path, rom: Path, shot: Path) -> dict:
    """Runs inside the child process."""
    import ctypes as C

    import libretro_harness as H

    class Pad(H.Frontend):
        def __init__(self, *a):
            super().__init__(*a)
            self.held: set[str] = set()
            cbs = list(self._cbs)
            cbs[5] = H.STATE_CB(self._pad)
            self._cbs = tuple(cbs)

        def _pad(self, port, device, index, button):
            if port != 0 or (device & 0xFF) != H.DEVICE_JOYPAD:
                return 0
            if button == H.JOYPAD_MASK:
                return sum(1 << BUTTONS[b] for b in self.held)
            return int(any(BUTTONS[b] == button for b in self.held))

        def ram(self, off: int, n: int) -> bytes:
            ptr = self.lib.retro_get_memory_data(H.MEMORY_SYSTEM_RAM)
            return C.string_at(ptr + off, n)

        def probe(self) -> dict:
            r = self.ram(PROBE, 16)
            return {
                "x": int.from_bytes(r[0:2], "little"),
                "y": int.from_bytes(r[2:4], "little", signed=True),
                "level": r[4],
                "state": r[5],
                "frame": int.from_bytes(r[10:12], "little"),
                "sig": list(r[12:16]),
            }

        def hold(self, frames: int, *buttons: str) -> None:
            self.held = set(buttons)
            self.run(frames)
            self.held = set()

    res: dict = {"problems": []}
    bad = res["problems"]
    with tempfile.TemporaryDirectory(prefix="rb-play-", ignore_cleanup_errors=True) as work:
        fe = Pad(core.resolve(), Path(work))
        if not fe.load(rom.resolve())["loaded"]:
            return {"problems": ["core refused the ROM"]}
        fe.hold(120)
        p = fe.probe()
        if p["sig"] != [0x52, 0x42, 1, 1]:
            bad.append(f"title signature {p['sig']}")
        fe.hold(6, "START")
        for _ in range(240):
            fe.hold(1)
            if fe.probe()["state"] == 2:
                break
        p = fe.probe()
        if p["sig"][3] != 2 or p["state"] != 2:
            bad.append(f"Start did not reach gameplay: {p}")
        x0 = p["x"]
        fe.hold(45, "RIGHT")
        p = fe.probe()
        res["moved_right"] = p["x"] - x0
        if p["x"] - x0 < 40:
            bad.append(f"holding Right moved the hero only {p['x'] - x0}px")
        fe.hold(10)
        y0 = fe.probe()["y"]
        lowest = y0
        for _ in range(25):
            fe.hold(1, "B")
            lowest = min(lowest, fe.probe()["y"])
        res["jump_height"] = y0 - lowest
        if y0 - lowest < 24:
            bad.append(f"B made the hero rise only {y0 - lowest}px")
        f0, emu, states = fe.probe()["frame"], 0, set()
        for i in range(1500 // 4):
            frames, buttons = SCRIPT[i % len(SCRIPT)]
            fe.hold(4 if frames >= 4 else frames, *buttons)
            emu += 4 if frames >= 4 else frames
            p = fe.probe()
            states.add(p["state"])
            if p["sig"][:3] != [0x52, 0x42, 1] or p["sig"][3] == 0xEE:
                bad.append(f"signature broken during play: {p['sig']}")
                break
        res["states_seen"] = sorted(states)
        res["pace"] = round(((fe.probe()["frame"] - f0) & 0xFFFF) / max(emu, 1), 3)
        if res["pace"] < 0.8:
            bad.append(f"game loop fell behind the emulator (pace {res['pace']})")
        if fe.frame:
            write_png(shot, fe.frame, fe.pixel_format)
        fe.close()
    return res


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cores", type=Path, default=ROOT / "tests" / "emulator" / ".cores")
    ap.add_argument("--out", type=Path, default=ROOT / "baked" / "play")
    ap.add_argument("--play", type=Path, help=argparse.SUPPRESS)
    ap.add_argument("--core", type=Path, help=argparse.SUPPRESS)
    ap.add_argument("--shot", type=Path, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    if args.play:  # child process
        print("RESULT " + json.dumps(play(args.core, args.play, args.shot)), flush=True)
        return 0

    ext = "dll" if sys.platform.startswith("win") else "so"
    core = args.cores / f"snes9x_libretro.{ext}"
    if not core.is_file():
        print(f"core missing: {core} (run tests/emulator/run_smoke.py --fetch-cores)")
        return 1
    failed = 0
    for rom in bake_samples(args.out):
        cmd = [sys.executable, __file__, "--play", str(rom), "--core", str(core)]
        cmd += ["--shot", str(rom.with_suffix(".png"))]
        try:
            proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
                cmd, capture_output=True, text=True, timeout=TIMEOUT_S, check=False
            )
            lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("RESULT ")]
            res = json.loads(lines[-1][7:]) if lines else {"problems": [proc.stderr[-800:]]}
        except subprocess.TimeoutExpired:
            res = {"problems": [f"hung: no result within {TIMEOUT_S}s"]}
        problems = res.get("problems", [])
        failed += bool(problems)
        detail = {k: v for k, v in res.items() if k != "problems"}
        print(
            f"{'PASS' if not problems else 'FAIL'}  {rom.name:<28} {detail} {'; '.join(problems)}"
        )
    print(f"\n{len(SAMPLES) - failed}/{len(SAMPLES)} play tests passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
