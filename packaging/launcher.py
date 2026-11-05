"""Entry point PyInstaller freezes into RetroBake.exe / the AppImage.

`RetroBake --self-test` bakes a sample NES platformer with the bundled tools and exits, so
CI (and anyone checking an install) can prove the frozen app works without opening a window.
"""

import sys


def self_test() -> int:
    from retrobake.builders import nes
    from retrobake.spec import new_spec

    spec, _ = new_spec("nes", "platformer", "a brave fox crosses the hills", "Fox", seed=3)
    rom = nes.bake(spec)
    print(f"self-test ok: {rom.engine} ROM, {len(rom.rom)} bytes, cc65 at {nes.find_cc65()}")
    return 0


if "--self-test" in sys.argv[1:]:
    raise SystemExit(self_test())

from retrobake.ui.app import main  # noqa: E402

raise SystemExit(main())
