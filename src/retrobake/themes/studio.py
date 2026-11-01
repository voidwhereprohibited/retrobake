"""RetroBake Theme Studio engine: one photo in -> complete RetroArch XMB theme out.

No paid AI: the photo is analysed locally (palette, brightness, saturation, pixel-art detection)
and the lettering style, accent colour, icon pack and icon effects are chosen by rules tuned on
community packs. Output (per theme contract):
  <out>/wallpapers/<tab or playlist name>.png   dynamic wallpapers (title top-left, XMB-safe)
  <out>/icons/<XMB icon name>.png                full XMB icon set (256x256 RGBA)
  <out>/preview.png                              XMB-layout preview
  <out>/theme.json                               what was chosen and why
User photos never leave the computer.
"""
from __future__ import annotations

import colorsys
import json
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

from PIL import Image, ImageStat

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/theme_art"))
import build_themes as BT  # noqa: E402
import lettering as LT  # noqa: E402

TABS = ["Main Menu", "Settings", "History", "Favorites", "Images", "Music", "Videos", "Netplay",
        "Import Content", "Explore", "Contentless Cores", "00 - Generic Background"]


@dataclass
class Analysis:
    brightness: float      # 0..1 mean luminance
    top_left: float        # 0..1 luminance where the title goes
    saturation: float      # 0..1 mean saturation
    pixel_art: bool
    accent: str            # most vivid dominant colour
    palette: list


def _hex(c):
    return "#%02x%02x%02x" % tuple(int(v) for v in c[:3])


def _axis_aligned(im) -> float:
    """Share of edge pixels whose edge is purely horizontal or vertical (pixel art ~1.0)."""
    W, H = 320, 180
    g = im.convert("L").resize((W, H), Image.NEAREST)
    px = list(g.get_flattened_data() if hasattr(g, "get_flattened_data") else g.getdata())
    edge = axis = 0
    for y in range(H - 1):
        row, nxt = y * W, (y + 1) * W
        for x in range(W - 1):
            gx = abs(px[row + x + 1] - px[row + x]); gy = abs(px[nxt + x] - px[row + x])
            if gx > 24 or gy > 24:
                edge += 1
                if min(gx, gy) < 0.15 * max(gx, gy):
                    axis += 1
    return 1.0 if edge < 50 else axis / edge


def analyze(photo: Path) -> Analysis:
    im = Image.open(photo).convert("RGB")
    small = im.copy(); small.thumbnail((320, 320))
    st = ImageStat.Stat(small.convert("HSV"))
    sat, val = st.mean[1] / 255, st.mean[2] / 255
    w, h = small.size
    tl = ImageStat.Stat(small.convert("L").crop((0, 0, int(w * .35), int(h * .15)))).mean[0] / 255
    tiny = im.copy(); tiny.thumbnail((256, 256), Image.NEAREST)
    data = tiny.get_flattened_data() if hasattr(tiny, "get_flattened_data") else tiny.getdata()
    uniq = len(set(data)) / (tiny.width * tiny.height)
    pixel = uniq < 0.06 and _axis_aligned(im) > 0.9
    q = small.quantize(colors=12, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()[:36]
    cols = [tuple(pal[i:i + 3]) for i in range(0, 36, 3)]
    counts = sorted(q.getcolors(), reverse=True)

    def vivid(c):
        hh, ss, vv = colorsys.rgb_to_hsv(*(x / 255 for x in c))
        return ss * vv
    weighted = [((vivid(cols[i]) ** 2) * (n ** .12), cols[i]) for n, i in counts if i < len(cols)]
    acc = max(weighted)[1] if weighted else (255, 60, 140)
    hh, ss, vv = colorsys.rgb_to_hsv(*(x / 255 for x in acc))   # same hue, always bright and clean
    acc = tuple(int(x * 255) for x in colorsys.hsv_to_rgb(hh, max(ss, .75), max(vv, .95)))
    return Analysis(val, tl, sat, pixel, _hex(acc), [_hex(cols[i]) for _, i in counts[:6] if i < len(cols)])


def choose(a: Analysis) -> dict:
    """Pick lettering + icon treatment from the analysis."""
    dark = a.brightness < .42
    vivid = a.saturation > .45
    if a.pixel_art:
        letter = {"kind": "mcblock", "font": "Silkscreen-Regular.ttf", "color": "#8f8f8f", "extrude": "#4a4a4a"} if not dark \
            else {"kind": "neon", "font": "PressStart2P-Regular.ttf", "color": a.accent}
        icons = {"pack": "16X-Theme-4-XMB/main icons/png", "fallback": "ra/xmb/dot-art/png",
                 "fx": {"outline": "#0d0d0d", "outline_px": 4, "shadow": True}, "systems": "yoshi-xmb"}
        why = "pixel-art photo -> blocky lettering and pixel icons"
    elif dark and vivid:
        letter = {"kind": "neon", "font": "TiltNeon.ttf", "color": a.accent}
        icons = {"pack": "baxy/Automatic/src/png/256", "fallback": "ra/xmb/monochrome/png",
                 "fx": {"glow": a.accent, "glow_strength": 1.3}, "systems": "rgci-xmb"}
        why = "dark, colourful photo -> neon tube lettering and glowing outline icons"
    elif dark:
        letter = {"kind": "chrome", "font": "Audiowide-Regular.ttf", "color": "#f2f2f2", "color2": a.accent,
                  "outline": "#101010", "glow": a.accent}
        icons = {"pack": "XMB-PS3-Icons-Sounds-Pack/ps3/PS3 Icons + Sounds/Icons/systematic/png",
                 "fallback": "baxy/Automatic/src/png/256", "fx": {"glow": a.accent, "glow_strength": .9},
                 "systems": "rgci-xmb"}
        why = "dark, muted photo -> chrome lettering and clean white icons with a soft glow"
    elif vivid:
        letter = {"kind": "comic", "font": "Bangers-Regular.ttf", "color": a.accent, "outline": "#111111", "tilt": 3}
        icons = {"pack": "baxy/FlatUX/src/png/256", "fallback": "baxy/RetroactiveRetired/src/png/256",
                 "fx": {"outline": "#111111", "outline_px": 4}, "systems": "rgci-xmb"}
        why = "bright, colourful photo -> bold comic lettering and full-colour icons"
    else:
        letter = {"kind": "stencil", "font": "BlackOpsOne-Regular.ttf", "color": "#1b1b1b", "color2": "#3a3a3a"}
        icons = {"pack": "baxy/RetroactiveRetired/src/png/256", "fallback": "baxy/Systematic/src/png/256",
                 "fx": {"shadow": True}, "systems": "rgci-xmb"}
        why = "bright, muted photo -> dark stencil lettering and tile icons"
    if a.top_left > .62 and letter["kind"] in ("neon", "chrome"):
        letter = {**letter, "kind": "comic", "font": "Bangers-Regular.ttf", "outline": "#111111"}
        why += " (title area is bright, so outlined lettering for contrast)"
    return {"letter": letter, "icons": icons, "why": why}


def build(photo: Path, out: Path, name: str, assets: Path, playlists: list[str] | None = None) -> dict:
    """assets = folder holding icon packs (_src layout) and fonts/."""
    a = analyze(photo); c = choose(a)
    out.mkdir(parents=True, exist_ok=True)
    bg = BT.cover(Image.open(photo).convert("RGB"), 3840, 2160).convert("RGBA")
    extra = set(LT.NAMES) - set(TABS) - {"Import Content"}
    names = TABS + sorted(set(playlists or []) | extra)
    wd = out / "wallpapers"; wd.mkdir(exist_ok=True)
    for n in names:
        im = bg.copy(); LT.place(im, LT.label(n), c["letter"], assets / "fonts")
        im.convert("RGB").save(wd / f"{n}.png", compress_level=1)
    t = {"pack": c["icons"]["pack"], "fallback": c["icons"]["fallback"], "fx": c["icons"]["fx"]}
    ic = BT.icons({}, assets, t, out / "icons")
    sysfx = {k: v for k, v in t["fx"].items() if k != "tint"}
    for f in (assets / c["icons"]["systems"]).glob("*.png"):
        im = BT.style_icon(Image.open(f), sysfx); im.save(out / "icons" / f.name); ic[f.stem] = im
    BT.contact(bg.convert("RGB"), ic, {"name": name}, out / "preview.png")
    meta = {"name": name, "photo": str(photo), "analysis": asdict(a), **c, "wallpapers": len(names)}
    (out / "theme.json").write_text(json.dumps(meta, indent=2))
    return meta


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Photo -> RetroArch XMB theme")
    ap.add_argument("photo"); ap.add_argument("--name", default="My Theme"); ap.add_argument("--out", required=True)
    ap.add_argument("--assets", required=True, help="folder with icon packs and fonts/")
    ap.add_argument("--analyze-only", action="store_true")
    x = ap.parse_args()
    if x.analyze_only:
        an = analyze(Path(x.photo)); print(json.dumps({**asdict(an), **choose(an)}, indent=2))
    else:
        print(json.dumps(build(Path(x.photo), Path(x.out), x.name, Path(x.assets)), indent=2))
