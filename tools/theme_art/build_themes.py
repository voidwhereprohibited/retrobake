#!/usr/bin/env python3
"""Build RetroArch XMB themes from a user's own wallpapers + existing open icon packs.

Icons are NOT drawn here: they come from libretro/retroarch-assets XMB packs
(CC-BY 4.0), recoloured to match the wallpaper (tint / gradient / glow / outline / shadow).

Input: a themes.json (see docs/themes/build_themes.md). Output per theme, next to the json:
  <id>/wallpapers/{master_3840x2160,1920x1200,1920x1080}.png
  <id>/icons/<exact XMB name>.png  (256x256 RGBA, every name in the primary pack + fallback)
  _previews/<id>.png               (1920x1200 contact sheet)

Usage: python3 tools/theme_art/build_themes.py /path/to/themes.json [theme-id ...]
"""
import json, os, subprocess, sys, tempfile
from pathlib import Path
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[2]
ESRGAN = ROOT / ".tools/realesrgan/realesrgan-ncnn-vulkan"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def cover(im, w, h):
    s = max(w / im.width, h / im.height)
    im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    x, y = (im.width - w) // 2, (im.height - h) // 2
    return im.crop((x, y, x + w, y + h))


def wallpaper(src, out):
    if (out / "master_3840x2160.png").exists():  # cached: upscaling is the slow part
        return Image.open(out / "master_3840x2160.png").convert("RGB")
    im = Image.open(src).convert("RGB")
    if im.width < 3840 or im.height < 2160:
        with tempfile.TemporaryDirectory() as t:
            a, b = Path(t) / "in.png", Path(t) / "out.png"
            im.save(a)
            subprocess.run([str(ESRGAN), "-i", str(a), "-o", str(b), "-n", "realesrgan-x4plus"],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            im = Image.open(b).convert("RGB")
    master = cover(im, 3840, 2160)
    out.mkdir(parents=True, exist_ok=True)
    master.save(out / "master_3840x2160.png")
    cover(master, 1920, 1200).save(out / "1920x1200.png")
    cover(master, 1920, 1080).save(out / "1920x1080.png")
    return master


def style_icon(ic, fx):
    ic = ic.convert("RGBA").resize((256, 256), Image.LANCZOS)
    pad = "glow" in fx or "outline" in fx or "shadow" in fx
    if pad:  # leave room for the effect
        ic = ic.resize((212, 212), Image.LANCZOS)
        c = Image.new("RGBA", (256, 256))
        c.paste(ic, (22, 22), ic)
        ic = c
    a = ic.getchannel("A")
    if "tint" in fx:
        lum = ic.convert("L")
        cols = [rgb(c) for c in fx["tint"]]
        if len(cols) == 1:
            col = Image.new("RGB", ic.size, cols[0])
        else:  # vertical gradient
            g = Image.linear_gradient("L").resize(ic.size)
            col = Image.composite(Image.new("RGB", ic.size, cols[1]), Image.new("RGB", ic.size, cols[0]), g)
        body = ImageChops.multiply(col, Image.merge("RGB", (lum, lum, lum)))
        ic = Image.merge("RGBA", (*body.split(), a))
    base = Image.new("RGBA", ic.size)
    if "shadow" in fx:
        sh = Image.new("RGBA", ic.size, (0, 0, 0, 0))
        sh.putalpha(a.point(lambda v: int(v * 0.75)))
        sh = sh.filter(ImageFilter.GaussianBlur(6))
        base.alpha_composite(sh, (5, 7))
    if "outline" in fx:
        n = fx.get("outline_px", 5) * 2 + 1
        ol = Image.new("RGBA", ic.size, rgb(fx["outline"]) + (0,))
        ol.putalpha(a.point(lambda v: 255 if v > 40 else 0).filter(ImageFilter.MaxFilter(n)))
        base.alpha_composite(ol)
    if "glow" in fx:
        k = fx.get("glow_strength", 1.0)
        gl = Image.new("RGBA", ic.size, rgb(fx["glow"]) + (0,))
        halo = a.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(9)) \
                .point(lambda v: min(255, int(v * 1.6 * k)))
        # glow only outside the icon silhouette, so holes and inner detail stay crisp
        outside = a.point(lambda v: 255 if v > 24 else 0)
        ImageDraw.floodfill(outside, (0, 0), 128)
        outside = outside.point(lambda v: 255 if v == 128 else 0)
        gl.putalpha(ImageChops.multiply(halo, outside))
        base.alpha_composite(gl)
    base.alpha_composite(ic)
    return base


def icons(cfg, root, t, out):
    out.mkdir(parents=True, exist_ok=True)
    prim, fb = root / t["pack"], root / t["fallback"]
    names = {p.name for p in fb.glob("*.png")} | {p.name for p in prim.glob("*.png")}
    done = {}
    for n in sorted(names):
        src = prim / n if (prim / n).exists() else fb / n
        im = style_icon(Image.open(src), t["fx"])
        im.save(out / n)
        done[n[:-4]] = im
    return done


def text(d, xy, s, size, fill=(255, 255, 255)):
    f = ImageFont.truetype(FONT, size)
    d.text((xy[0] + 2, xy[1] + 3), s, font=f, fill=(0, 0, 0))
    d.text(xy, s, font=f, fill=fill)


def contact(master, ic, t, dest):
    W, H = 1920, 1200
    im = cover(master, W, H).convert("RGBA")
    d = ImageDraw.Draw(im)
    pick = lambda *ns: next((ic[n] for n in ns if n in ic), None)
    tabs = [pick("main-menu", "setting"), pick("setting"), pick("history"), pick("favorites"),
            pick("Nintendo - Nintendo Entertainment System"), pick("Nintendo - Super Nintendo Entertainment System"),
            pick("netplay"), pick("add")]
    x0, y0 = 260, 210
    for i, t_ in enumerate(t for t in tabs if t is not None):
        sz = 190 if i == 1 else 128
        cx = x0 + i * 200 + (0 if i < 2 else 50)
        im.alpha_composite(t_.resize((sz, sz), Image.LANCZOS), (cx - sz // 2, y0 - sz // 2))
    text(d, (x0 + 200 - 80, y0 + 105), "Settings", 34)
    rows = [("Core Options", "core-options"), ("Save State", "savestate"), ("Load State", "loadstate"),
            ("Screenshot", "screenshot"), ("Wi-Fi", "wifi"), ("Netplay", "netplay"), ("Undo", "undo")]
    for j, (label, n) in enumerate(rows):
        y = y0 + 185 + j * 90
        r = pick(n, "setting")
        im.alpha_composite(r.resize((72, 72), Image.LANCZOS), (x0 + 150, y - 10))
        text(d, (x0 + 245, y), label, 46 if j == 0 else 36)
    text(d, (40, H - 70), t["name"], 36)
    dest.parent.mkdir(parents=True, exist_ok=True)
    im.convert("RGB").save(dest)


def main():
    cfgp = Path(sys.argv[1]).expanduser().resolve()
    cfg = json.loads(cfgp.read_text())
    base = cfgp.parent
    root = (base / cfg["icon_root"]).resolve()
    want = set(sys.argv[2:])
    for t in cfg["themes"]:
        if want and t["id"] not in want:
            continue
        print(f"== {t['id']}", flush=True)
        m = wallpaper(Path(os.path.expanduser(t["wallpaper"])), base / t["id"] / "wallpapers")
        ic = icons(cfg, root, t, base / t["id"] / "icons")
        contact(m, ic, t, base / "_previews" / f"{t['id']}.png")
        print(f"   {len(ic)} icons, preview _previews/{t['id']}.png", flush=True)


if __name__ == "__main__":
    main()
