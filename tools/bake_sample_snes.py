"""Bake RetroBake's sample SNES ROMs (used by CI and qa's emulator smoke test).

    python tools/bake_sample_snes.py OUT.sfc

Writes OUT.sfc (the platformer engine) and OUT-topdown.sfc (a top-down spec, which still uses
the title-screen placeholder engine until the top-down engine lands).
"""

from __future__ import annotations

import sys
from pathlib import Path

from retrobake import spec as gs
from retrobake.builders import snes

SAMPLES = (("", ["platformer"], "Hello RetroBake"), ("-topdown", ["topdown_adventure"], "Top Down"))


def main(argv: list[str]) -> int:
    out = Path(argv[1] if len(argv) > 1 else "sample-platformer.sfc")
    out.parent.mkdir(parents=True, exist_ok=True)
    for suffix, genres, title in SAMPLES:
        spec, _ = gs.new_spec("snes", genres, "a sample game", title, seed=1)
        try:
            result = snes.bake(spec)
        except snes.SnesBuildError as exc:
            print(f"bake failed: {exc.message}\n{exc.detail}", file=sys.stderr)
            return 1
        path = out.with_name(out.stem + suffix + out.suffix)
        path.write_bytes(result.rom)
        print(
            f"wrote {path} ({len(result.rom)} bytes, engine {result.engine}, "
            f"network isolated: {result.network_isolated})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
