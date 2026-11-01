#!/usr/bin/env python3
"""Build a RetroArch XMB *dynamic wallpaper* set per theme (one image per tab + per system playlist),
the way community packs (Vriom, Shakabello) are made: shared background + per-entry console art +
name + accent color. Files are named exactly like XMB tab titles / playlist names.

Console art: BAXY Systematic 1024px (MIT). Tab art: the theme's own icon set.
Usage: build_dynamic.py themes.json names_dir [theme-id ...]
  names_dir = a folder whose *.png names define the file list (e.g. an existing pack like Vriom).
"""
import json, os, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
TABS = {"Main Menu": "main-menu", "Settings": "setting", "History": "history", "Favorites": "favorites",
        "Images": "images", "Music": "music", "Videos": "video", "Netplay": "netplay",
        "Import Content": "add", "Explore": "explore", "Content": "playlist", "00 - Generic Background": None}


def rgb(h):
    h = h.lstrip("#"); return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def accent(fx):
    for k in ("glow", "outline"):
        if k in fx and fx[k].lower() not in ("#000000", "#0d0d0d", "#2b1d14", "#ffffff"):
            return rgb(fx[k])
    if "tint" in fx:
        return rgb(fx["tint"][-1])
    return (230, 40, 40)


def glow_text(base, xy, s, size, col):
    f = ImageFont.truetype(FONT, size)
    lay = Image.new("RGBA", base.size)
    d = ImageDraw.Draw(lay)
    d.text(xy, s, font=f, fill=col + (255,))
    g = lay.filter(ImageFilter.GaussianBlur(size // 6))
    base.alpha_composite(g); base.alpha_composite(g)
    sh = Image.new("RGBA", base.size); ImageDraw.Draw(sh).text((xy[0] + 4, xy[1] + 5), s, font=f, fill=(0, 0, 0, 200))
    base.alpha_composite(sh)
    ImageDraw.Draw(base).text(xy, s, font=f, fill=(255, 255, 255, 255))


def art_for(name, icons, consoles):
    if name in TABS:
        k = TABS[name]
        return (Image.open(icons / f"{k}.png").convert("RGBA") if k and (icons / f"{k}.png").exists() else None), True
    for n in (name, name.replace(" (alt)", "").replace(" (E)", "").replace(" (J)", "").replace(" (PSN)", "")):
        if (consoles / f"{n}.png").exists():
            return Image.open(consoles / f"{n}.png").convert("RGBA"), False
    return None, False


def build(theme, base_dir, names, consoles, out_root):
    W, H = 3840, 2160
    bg = Image.open(base_dir / theme["id"] / "wallpapers" / "master_3840x2160.png").convert("RGBA")
    # legibility band: soft dark gradient along the bottom where art + name sit
    grad = Image.linear_gradient("L").resize((W, H)).point(lambda v: max(0, v - 110) * 255 // 145 * 0.75)
    shade = Image.new("RGBA", (W, H), (0, 0, 0, 0)); shade.putalpha(grad.convert("L"))
    base = bg.copy(); base.alpha_composite(shade)
    acc = accent(theme["fx"])
    icons = base_dir / theme["id"] / "icons"
    out = out_root / f"RetroBake - {theme['name']}"
    out.mkdir(parents=True, exist_ok=True)
    for name in names:
        im = base.copy()
        art, is_tab = art_for(name, icons, consoles)
        if art is not None:
            bb = art.getbbox(); art = art.crop(bb) if bb else art
            box = 760 if is_tab else 1250
            art.thumbnail((box, box), Image.LANCZOS)
            if art.width < box * 0.6 and art.height < box * 0.6:  # small source: scale up to fill
                s = box * 0.8 / max(art.size); art = art.resize((int(art.width * s), int(art.height * s)), Image.LANCZOS)
            x, y = W - art.width - 220, H - art.height - 200
            sh = Image.new("RGBA", art.size, (0, 0, 0, 0)); sh.putalpha(art.getchannel("A").point(lambda v: int(v * .7)))
            halo = Image.new("RGBA", art.size, acc + (0,)); halo.putalpha(art.getchannel("A").filter(ImageFilter.GaussianBlur(30)).point(lambda v: int(v * .55)))
            pad = 80
            for layer, off in ((halo, (0, 0)), (sh.filter(ImageFilter.GaussianBlur(25)), (25, 35))):
                big = Image.new("RGBA", (W, H)); big.paste(layer, (x + off[0], y + off[1])); im.alpha_composite(big)
            im.alpha_composite(art, (x, y))
        if name != "00 - Generic Background":
            maker, _, sysname = name.partition(" - ")
            title, sub = (sysname, maker) if sysname else (name, "")
            ImageDraw.Draw(im).rectangle((200, H - 470, 216, H - 200), fill=acc + (255,))
            if sub:
                glow_text(im, (260, H - 470), sub.upper(), 70, acc)
            size = 150 if len(title) < 18 else 118 if len(title) < 26 else 92
            glow_text(im, (255, H - 380), title, size, acc)
        im.convert("RGB").save(out / f"{name}.png")
    return out


def main():
    cfgp = Path(sys.argv[1]).expanduser().resolve(); cfg = json.loads(cfgp.read_text())
    names = sorted(p.stem for p in Path(sys.argv[2]).expanduser().glob("*.png"))
    want = set(sys.argv[3:])
    consoles = cfgp.parent / "_src/baxy/Systematic/src/png/1024"
    out_root = Path(os.path.expanduser("~/.config/retroarch/wallpapers"))
    for t in cfg["themes"]:
        if want and t["id"] not in want:
            continue
        o = build(t, cfgp.parent, names, consoles, out_root)
        print(f"{t['id']}: {len(list(o.glob('*.png')))} wallpapers -> {o}", flush=True)


if __name__ == "__main__":
    main()
