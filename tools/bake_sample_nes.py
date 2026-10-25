"""Bake RetroBake's sample "hello" NES ROM (used by CI and qa's emulator smoke test).

    python tools/bake_sample_nes.py OUT.nes
"""

from __future__ import annotations

import sys
from pathlib import Path

from retrobake import spec as gs
from retrobake.builders import nes


def main(argv: list[str]) -> int:
    out = Path(argv[1] if len(argv) > 1 else "sample-hello.nes")
    spec, _ = gs.new_spec("nes", ["platformer"], "a sample game", "Hello RetroBake", seed=1)
    try:
        result = nes.bake(spec)
    except nes.NesBuildError as exc:
        print(f"bake failed: {exc.message}\n{exc.detail}", file=sys.stderr)
        return 1
    out.write_bytes(result.rom)
    print(f"wrote {out} ({len(result.rom)} bytes, network isolated: {result.network_isolated})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
