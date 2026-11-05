"""Take the README screenshots: every wizard screen at 1366x768, rendered offscreen.

    QT_QPA_PLATFORM=offscreen python tools/readme_screenshots.py [docs/screenshots]

Walks the real wizard with a sample idea (and a real bake, so cc65 must be available,
e.g. RETROBAKE_CC65_DIR). The in-game shot comes from tests/emulator/play_platformer.py:
    python tests/emulator/play_platformer.py --core <fceumm> --rom <game.nes> --frames 60 \
        --shot 40 docs/screenshots/09-playing-in-fceumm.png
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from retrobake.ui.app import create_app, create_window  # noqa: E402

IDEA = "A brave fox explores misty green hills, collects keys and stomps on beetles."
NAMES = ["welcome", "system", "genre", "describe", "questions", "cover-name", "bake", "finish"]


def settle(app, seconds: float = 0.3) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()


def main(argv: list[str]) -> int:
    out = Path(argv[1] if len(argv) > 1 else "docs/screenshots")
    out.mkdir(parents=True, exist_ok=True)
    app = create_app([])
    win = create_window(app)
    win.resize(1366, 768)
    win.show()
    for i, name in enumerate(NAMES):
        step = win.current
        if name == "describe":
            step.text.setPlainText(IDEA)
            step.show_plan()
        if name == "bake":
            step.start()
            deadline = time.monotonic() + 60
            while not step.is_complete() and time.monotonic() < deadline:
                settle(app, 0.1)
            if not step.is_complete():
                print("bake didn't finish:", step.status.text(), file=sys.stderr)
                return 1
        settle(app)
        path = out / f"{i + 1:02d}-{name}.png"
        win.grab().save(str(path))
        print("saved", path, win.width(), "x", win.height())
        if i + 1 < len(NAMES):
            win.go_next()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
