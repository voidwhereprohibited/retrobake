#!/usr/bin/env python3
"""RetroBake theme-art preview builder (theme-art agent tool, not shipped in the app).

For each style in themes/styles.json:
  1. generate a wallpaper + an icon sheet with Pollinations (fixed seed per style)
  2. upscale the wallpaper 4x with Real-ESRGAN (realesrgan-x4plus) -> 3840x2160 master
  3. export 1920x1200 and 1920x1080 PNGs
  4. cut the icon sheet into 256x256 transparent PNGs
  5. render a 1920x1200 contact sheet (wallpaper + XMB icon row + menu text)

Key: put a Pollinations secret key (sk_...) in ~/.config/retrobake/pollinations.key (chmod 600)
or POLLINATIONS_KEY. Without a key it falls back to the keyless Classic API, which only gives
1024x576 'sana' drafts at 1 image / 45 s - below the quality bar, drafts only.

Usage: python3 tools/theme_art/make_previews.py [style-id ...]
"""
import io, json, os, subprocess, sys, time, urllib.parse, urllib.request
from pathlib import Path
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[2]
STYLES = json.loads((ROOT / "themes/styles.json").read_text())
WORK = ROOT / "themes/_work"
OUT = ROOT / "themes/_previews"
ESRGAN = ROOT / ".tools/realesrgan/realesrgan-ncnn-vulkan"
MODEL = os.environ.get("RB_MODEL", "tongyi-mai/z-image-turbo")


def key():
    k = os.environ.get("POLLINATIONS_KEY")
    p = Path.home() / ".config/retrobake/pollinations.key"
    if not k and p.exists():
        k = p.read_text().strip()
    return k or None


def fetch(prompt, w, h, seed, dest):
    if dest.exists():
        return dest
    k = key()
    q = urllib.parse.quote(prompt[:1800], safe="")
    if k:
        url = f"https://gen.pollinations.ai/image/{q}?" + urllib.parse.urlencode(
            {"model": MODEL, "width": w, "height": h, "seed": seed, "nologo": "true", "safe": "true"})
        hdr = {"Authorization": f"Bearer {k}"}
    else:
        url = f"https://image.pollinations.ai/prompt/{q}?" + urllib.parse.urlencode(
            {"width": w, "height": h, "seed": seed, "nologo": "true"})
        hdr = {}
    for attempt in range(12):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "RetroBake-theme-art", **hdr})
            with urllib.request.urlopen(req, timeout=240) as r:
                data = r.read()
            im = Image.open(io.BytesIO(data)).convert("RGB")  # validates it is an image
            dest.parent.mkdir(parents=True, exist_ok=True)
            im.save(dest)
            print(f"  got {dest.name} {im.size}", flush=True)
            if not k:
                time.sleep(46)
            return dest
        except Exception as e:  # rate limit / busy: back off and retry
            print(f"  retry {attempt+1}: {e}", flush=True)
            time.sleep(50 if not k else 10)
    raise SystemExit(f"failed to generate {dest}")


def upscale(src, dest):
    if not dest.exists():
        subprocess.run([str(ESRGAN), "-i", str(src), "-o", str(dest), "-n", "realesrgan-x4plus"],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return dest


def cover(im, w, h):
    s = max(w / im.width, h / im.height)
    im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    l, t = (im.width - w) // 2, (im.height - h) // 2
    return im.crop((l, t, l + w, t + h))


def cut_icons(sheet, n):
    """Split a 3x2 sheet into n 256x256 RGBA icons.

    The model's "magenta" key drifts (often hot pink ~(230,37,146)), so each cell's
    background colour is sampled from its border and removed by flood fill from the
    edges, plus a tight global pass for enclosed holes (e.g. inside a gear)."""
    sheet = sheet.convert("RGB")
    icons, cw, ch = [], sheet.width // 3, sheet.height // 2
    for i in range(n):
        cell = sheet.crop(((i % 3) * cw, (i // 3) * ch, (i % 3 + 1) * cw, (i // 3 + 1) * ch))
        w, h = cell.size
        border = [cell.getpixel((x, y)) for x in range(0, w, 8) for y in (0, 1, h - 2, h - 1)] + \
                 [cell.getpixel((x, y)) for y in range(0, h, 8) for x in (0, 1, w - 2, w - 1)]
        border.sort(key=sum)
        bg = border[len(border) // 2]
        mask = Image.new("L", (w, h), 0)
        px, mp = cell.load(), mask.load()

        def near(c, t):
            return (c[0] - bg[0]) ** 2 + (c[1] - bg[1]) ** 2 + (c[2] - bg[2]) ** 2 < t * t
        stack = [(x, y) for x in range(w) for y in (0, h - 1)] + [(x, y) for y in range(h) for x in (0, w - 1)]
        while stack:
            x, y = stack.pop()
            if mp[x, y] or not near(px[x, y], 95):
                continue
            mp[x, y] = 255
            if x > 0: stack.append((x - 1, y))
            if x < w - 1: stack.append((x + 1, y))
            if y > 0: stack.append((x, y - 1))
            if y < h - 1: stack.append((x, y + 1))
        for y in range(h):
            for x in range(w):
                if not mp[x, y] and near(px[x, y], 40):
                    mp[x, y] = 255
        mask = mask.filter(ImageFilter.MaxFilter(3))  # 1px choke: no pink fringe on the outline
        rgba = cell.convert("RGBA")
        rgba.putalpha(Image.eval(mask, lambda v: 255 - v))
        bb = rgba.getbbox() or (0, 0, w, h)
        rgba = rgba.crop(bb)
        rgba.thumbnail((232, 232), Image.LANCZOS)
        ic = Image.new("RGBA", (256, 256))
        ic.paste(rgba, ((256 - rgba.width) // 2, (256 - rgba.height) // 2), rgba)
        icons.append(ic)
    return icons


def font(size):
    for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf"):
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def text(d, xy, s, f, fill=(255, 255, 255)):
    x, y = xy
    d.text((x + 3, y + 3), s, font=f, fill=(0, 0, 0, 170))
    d.text((x, y), s, font=f, fill=fill)


def contact_sheet(wall, icons, names, style, draft):
    W, H = 1920, 1200
    im = cover(wall, W, H).convert("RGBA")
    d = ImageDraw.Draw(im)
    x0, y0 = 300, 210
    for i, ic in enumerate(icons):
        sz = 176 if i == 1 else 120
        icx = ic.resize((sz, sz), Image.LANCZOS)
        cx = x0 + i * 230 + (0 if i < 2 else 60)
        im.alpha_composite(icx, (cx - sz // 2, y0 - sz // 2))
    text(d, (x0 + 230 - 90, y0 + 100), names[1].title(), font(34))
    items = ["Load Core", "Load Content", "Online Updater", "Information", "Configuration File", "Quit RetroArch"]
    for j, it in enumerate(items):
        sz = 46 if j == 0 else 36
        icx = icons[min(j, len(icons) - 1)].resize((64, 64), Image.LANCZOS)
        y = y0 + 190 + j * 92
        im.alpha_composite(icx, (x0 + 160, y - 6))
        text(d, (x0 + 250, y), it, font(sz), (255, 255, 255) if j == 0 else (235, 235, 235))
    tag = f"{style['name']}" + ("   [DRAFT - keyless low-res source]" if draft else "")
    text(d, (40, H - 70), tag, font(36))
    return im.convert("RGB")


def run(style):
    sid, seed = style["id"], style["seed"]
    print(f"== {sid}", flush=True)
    draft = key() is None
    w, h = (1024, 576) if draft else (1920, 1080)
    wp = STYLES["wallpaper_template"].format(scene=style["scene"])
    raw = fetch(wp, w, h, seed, WORK / sid / "wall_raw.png")
    up = upscale(raw, WORK / sid / "wall_x4.png")
    master = cover(Image.open(up).convert("RGB"), 3840, 2160)
    master = ImageEnhance.Sharpness(master).enhance(1.15)
    d = ROOT / "themes" / sid / "wallpapers"
    d.mkdir(parents=True, exist_ok=True)
    master.save(d / "master_3840x2160.png", optimize=True)
    cover(master, 1920, 1200).save(d / "1920x1200.png", optimize=True)
    cover(master, 1920, 1080).save(d / "1920x1080.png", optimize=True)
    subj = STYLES["icon_subjects"]
    ip = STYLES["icon_template"].format(icons="; ".join(f"{i+1}) {s}" for i, (_, s) in enumerate(subj)),
                                        icon_style=style["icon_style"])
    sheet = Image.open(fetch(ip, 1536 if not draft else 1024, 1024 if not draft else 683, seed, WORK / sid / "icons_raw.png"))
    icons = cut_icons(sheet, len(subj))
    idir = ROOT / "themes" / sid / "icons_sample"
    idir.mkdir(parents=True, exist_ok=True)
    for (n, _), ic in zip(subj, icons):
        ic.save(idir / f"{n}.png", optimize=True)
    OUT.mkdir(parents=True, exist_ok=True)
    contact_sheet(master, icons, [n for n, _ in subj], style, draft).save(OUT / f"{sid}.png", optimize=True)
    print(f"  contact sheet -> themes/_previews/{sid}.png", flush=True)


if __name__ == "__main__":
    want = set(sys.argv[1:])
    for s in STYLES["styles"]:
        if not want or s["id"] in want:
            run(s)
