"""Plays a baked NES platformer ROM in a real libretro core (FCEUmm) and prints one JSON line.

Run in a child process by test_platformer_emulator.py, like libretro_harness.py is by
run_smoke.py. It starts the game, holds Right with a jump now and then, and reads the
engine's qa block ($07F0: lives, camera x, enemies alive, level, hero x/y) every frame.

Usage: python play_platformer.py --core <fceumm_libretro.so> --rom <game.nes>
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from libretro_harness import JOYPAD_A, JOYPAD_RIGHT, Frontend, frame_stats  # noqa: E402

QA = 0x07F0


def qa(fe: Frontend) -> dict:
    lives, cam_lo, cam_hi, alive, level, hx_lo, hx_hi, hy = fe.ram(QA, 8)
    return {"lives": lives, "cam": cam_lo | cam_hi << 8, "alive": alive, "level": level}


def play(fe: Frontend, frames: int) -> dict:
    fe.run(120)
    title = fe.signature("nes")
    fe.start_down = True
    fe.run(5)
    fe.start_down = False
    fe.run(60)
    start = qa(fe)
    cams, deaths = [], 0
    for i in range(frames):
        fe.held = {JOYPAD_RIGHT} | ({JOYPAD_A} if i % 40 < 3 else set())
        fe.run(1)
        now = qa(fe)
        if now["lives"] < (cams[-1]["lives"] if cams else start["lives"]):
            deaths += 1
        cams.append(now)
    steps = [b["cam"] - a["cam"] for a, b in zip(cams, cams[1:], strict=False)]
    return {
        "sig_title": title,
        "sig_playing": fe.signature("nes"),
        "start": start,
        "max_cam": max(c["cam"] for c in cams),
        "max_cam_step": max(steps),
        "deaths": deaths,
        "end": cams[-1],
        "frame": frame_stats(fe.frame, fe.pixel_format),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--core", type=Path, required=True)
    ap.add_argument("--rom", type=Path, required=True)
    ap.add_argument("--frames", type=int, default=600)
    args = ap.parse_args(argv)
    with tempfile.TemporaryDirectory(prefix="rb-play-", ignore_cleanup_errors=True) as work:
        fe = Frontend(args.core.resolve(), Path(work))
        result = fe.load(args.rom.resolve())
        if result["loaded"]:
            result.update(play(fe, args.frames))
            fe.close()
    print("RESULT " + json.dumps(result), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
