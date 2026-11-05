#!/usr/bin/env python3
"""Render icon-pack options for one theme on its own wallpaper (2x3 grid, labeled A-F).
Usage: icon_options.py themes.json options.json"""
import json, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
sys.path.insert(0, str(Path(__file__).parent))
import build_themes as B

NEED = ["main-menu", "setting", "history", "favorites", "Nintendo - Nintendo Entertainment System",
        "Nintendo - Super Nintendo Entertainment System", "netplay", "add", "core-options", "savestate",
        "loadstate", "screenshot", "wifi", "undo"]


def main():
    cfgp = Path(sys.argv[1]).expanduser().resolve(); base = cfgp.parent
    root = (base / json.loads(cfgp.read_text())["icon_root"]).resolve()
    opts = json.loads(Path(sys.argv[2]).read_text())
    f = ImageFont.truetype(B.FONT, 64)
    for tid, choices in opts.items():
        master = Image.open(base / tid / "wallpapers" / "master_3840x2160.png").convert("RGB")
        grid = Image.new("RGB", (1920 * 2, 1200 * 3))
        for i, ch in enumerate(choices):
            ic = {}
            for n in NEED:
                for p in (ch["pack"], ch.get("fallback", ch["pack"])):
                    fp = root / p / f"{n}.png"
                    if fp.exists():
                        ic[n] = B.style_icon(Image.open(fp), ch["fx"]); break
            tmp = base / "_previews" / "_opt.png"
            B.contact(master, ic, {"name": ""}, tmp)
            im = Image.open(tmp).convert("RGB")
            d = ImageDraw.Draw(im)
            lab = f"{chr(65 + i)}  {ch['label']}"
            d.rectangle((0, 1200 - 120, 1920, 1200), fill=(0, 0, 0))
            d.text((40, 1200 - 105), lab, font=f, fill=(255, 255, 255))
            grid.paste(im, ((i % 2) * 1920, (i // 2) * 1200))
        grid.save(base / "_previews" / f"OPTIONS-{tid}.png")
        grid.resize((1280, 1200)).save(base / "_previews" / f"OPTIONS-{tid}-small.jpg", quality=85)
        print("done", tid, flush=True)


if __name__ == "__main__":
    main()
