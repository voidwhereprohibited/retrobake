#!/usr/bin/env python3
"""Build one XMB dynamic-wallpaper folder per theme: theme photo + styled name (upper-left) per tab/playlist.
Usage: build_lettered.py themes.json names_dir [theme-id ...]"""
import json, os, sys
from pathlib import Path
from PIL import Image
sys.path.insert(0, str(Path(__file__).parent))
import lettering as L


def main():
    cfgp = Path(sys.argv[1]).expanduser().resolve(); base = cfgp.parent
    names = sorted(p.stem for p in Path(sys.argv[2]).expanduser().glob("*.png"))
    want = set(sys.argv[3:]); fd = base / "_src/fonts"
    root = Path(os.path.expanduser("~/.config/retroarch/wallpapers"))
    for t in json.loads(cfgp.read_text())["themes"]:
        if want and t["id"] not in want:
            continue
        bg = Image.open(base / t["id"] / "wallpapers" / "master_3840x2160.png").convert("RGBA")
        out = root / f"RetroBake - {t['name']}"; out.mkdir(parents=True, exist_ok=True)
        for n in names:
            im = bg.copy(); L.place(im, L.label(n), t["letter"], fd)
            im.convert("RGB").save(out / f"{n}.png", compress_level=1)
        print(f"{t['name']}: {len(names)} -> {out}", flush=True)


if __name__ == "__main__":
    main()
