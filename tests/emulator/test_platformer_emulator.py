"""The baked NES platformer, played in the FCEUmm libretro core (the one RetroArch uses).

Needs cc65 and a FCEUmm core; skips without them. Set RETROBAKE_FCEUMM_CORE to the core's
path, or keep it where RetroArch installs it (~/.config/retroarch/cores/).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from retrobake import spec as gs
from retrobake.builders import nes

HERE = Path(__file__).resolve().parent
DEFAULT_CORE = Path.home() / ".config/retroarch/cores/fceumm_libretro.so"


def _core() -> Path | None:
    core = Path(os.environ.get("RETROBAKE_FCEUMM_CORE", DEFAULT_CORE))
    return core if core.is_file() else None


def _rom(tmp_path: Path) -> Path:
    try:
        nes.find_cc65()
    except nes.NesBuildError:
        pytest.skip("cc65 not found (set RETROBAKE_CC65_DIR)")
    spec, _ = gs.new_spec("nes", "platformer", "a brave fox crosses the hills", "Fox", seed=3)
    rom = tmp_path / "fox.nes"
    rom.write_bytes(nes.bake(spec).rom)
    return rom


@pytest.mark.skipif(_core() is None, reason="no FCEUmm libretro core here")
def test_platformer_plays_in_fceumm(tmp_path):
    rom = _rom(tmp_path)
    cmd = [sys.executable, str(HERE / "play_platformer.py"), "--core", str(_core())]
    out = subprocess.run(  # noqa: S603 - our own script, fixed arguments
        [*cmd, "--rom", str(rom)], capture_output=True, text=True, timeout=120, check=True
    )
    line = next(x for x in out.stdout.splitlines() if x.startswith("RESULT "))
    result = json.loads(line[len("RESULT ") :])
    print(json.dumps(result, indent=1))  # shows up with pytest -s: which core, what happened
    assert result["loaded"] and "FCEUmm" in result["core"]
    assert result["sig_title"] == [0x52, 0x42, 1, 1]
    assert result["start"]["lives"] == 3 and result["start"]["cam"] == 0
    assert result["start"]["alive"] > 0  # enemies placed
    assert result["max_cam"] > 32  # the camera followed the hero
    assert 0 < result["max_cam_step"] <= 2  # pixel by pixel, no screen flips
    # Running blindly into the level costs lives; each one restarts it with fewer hearts.
    assert result["deaths"] >= 1
    assert result["end"]["lives"] == 3 - result["deaths"] or result["sig_playing"][3] == 1
    assert result["frame"]["nonblack"] > 0.5
