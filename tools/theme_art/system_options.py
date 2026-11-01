#!/usr/bin/env python3
"""For every theme: render its wallpaper with the XMB layout, once per system-icon pack, side by side.
Menu icons = the theme's own built set; system icons = full-color pack (only glow/shadow/outline fx, no tint).
Usage: system_options.py themes.json label=dir [label=dir ...]"""
import json, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
sys.path.insert(0, str(Path(__file__).parent))
import build_themes as B

TOP = ["setting", "history", "favorites", "Nintendo - Nintendo Entertainment System",
       "Nintendo - Super Nintendo Entertainment System", "Nintendo - Nintendo 64", "Sega - Mega Drive - Genesis",
       "Sony - PlayStation", "Nintendo - Game Boy Advance"]
ROWS = [("Core Options", "core-options"), ("Save State", "savestate"), ("Load State", "loadstate"),
        ("Screenshot", "screenshot"), ("Wi-Fi", "wifi"), ("Netplay", "netplay"), ("Undo", "undo")]


def render(master, menu, sysdir, fx, label):
    W, H = 1920, 1200
    im = B.cover(master, W, H).convert("RGBA"); d = ImageDraw.Draw(im)
    sfx = {k: v for k, v in fx.items() if k != "tint"}
    x0, y0 = 200, 210
    for i, n in enumerate(TOP):
        p = sysdir / f"{n}.png"
        ic = B.style_icon(Image.open(p), sfx) if n.startswith(("Nintendo", "Sega", "Sony")) and p.exists() else menu.get(n)
        if ic is None:
            continue
        sz = 170 if i == 1 else 120
        cx = x0 + i * 180 + (0 if i < 2 else 40)
        im.alpha_composite(ic.resize((sz, sz), Image.LANCZOS), (cx - sz // 2, y0 - sz // 2))
    B.text(d, (x0 + 180 - 70, y0 + 100), "History", 34)
    for j, (lab, n) in enumerate(ROWS):
        y = y0 + 185 + j * 90
        r = menu.get(n) or menu.get("setting")
        if r: im.alpha_composite(r.resize((72, 72), Image.LANCZOS), (x0 + 130, y - 10))
        B.text(d, (x0 + 225, y), lab, 46 if j == 0 else 36)
    d.rectangle((0, H - 110, W, H), fill=(0, 0, 0, 255))
    B.text(d, (40, H - 95), label, 60)
    return im.convert("RGB")


def main():
    cfgp = Path(sys.argv[1]).expanduser().resolve(); base = cfgp.parent
    packs = [a.split("=", 1) for a in sys.argv[2:]]
    for t in json.loads(cfgp.read_text())["themes"]:
        master = Image.open(base / t["id"] / "wallpapers" / "master_3840x2160.png").convert("RGB")
        idir = base / t["id"] / "icons"
        menu = {n: Image.open(idir / f"{n}.png").convert("RGBA") for _, n in ROWS + [("", "setting"), ("", "history"), ("", "favorites")]
                if (idir / f"{n}.png").exists()}
        grid = Image.new("RGB", (1920 * len(packs), 1200))
        for i, (lab, d) in enumerate(packs):
            grid.paste(render(master, menu, base / d, t["fx"], f"{t['name']}  -  {chr(65 + i)}: {lab}"), (i * 1920, 0))
        grid.save(base / "_previews" / f"SYSTEMS-{t['id']}.png")
        print("done", t["id"], flush=True)


if __name__ == "__main__":
    main()
