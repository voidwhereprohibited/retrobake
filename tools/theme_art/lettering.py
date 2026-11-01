#!/usr/bin/env python3
"""Styled title lettering for XMB dynamic wallpapers (upper-left corner, above the XMB icon row)."""
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

NAMES = {
    "Nintendo - Nintendo Entertainment System": "NES", "Nintendo - Family Computer": "Famicom",
    "Nintendo - Family Computer Disk System": "Disk System", "Nintendo - Super Nintendo Entertainment System": "Super Nintendo",
    "Nintendo - Super Nintendo Entertainment System (E)": "Super Nintendo", "Nintendo - Super Famicom": "Super Famicom",
    "Nintendo - Nintendo 64": "Nintendo 64", "Nintendo - Nintendo 64DD": "64DD", "Nintendo - GameCube": "GameCube",
    "Nintendo - Game Boy": "Game Boy", "Nintendo - Game Boy Color": "Game Boy Color", "Nintendo - Game Boy Advance": "Game Boy Advance",
    "Nintendo - Nintendo DS": "Nintendo DS", "Nintendo - Nintendo 3DS": "Nintendo 3DS", "Nintendo - Virtual Boy": "Virtual Boy",
    "Nintendo - Wii": "Wii", "Nintendo - Wii U": "Wii U", "Sega - Mega Drive - Genesis": "Genesis",
    "Sega - Mega Drive - Genesis (E)": "Mega Drive", "Sega - Mega Drive - Genesis (J)": "Mega Drive",
    "Sega - Master System - Mark III": "Master System", "Sega - Master System - Mark III (alt)": "Mark III",
    "Sega - Game Gear": "Game Gear", "Sega - Mega-CD - Sega CD": "Sega CD", "Sega - 32X": "32X", "Sega - Saturn": "Saturn",
    "Sega - Dreamcast": "Dreamcast", "Sega - SG-1000": "SG-1000", "Sony - PlayStation": "PlayStation",
    "Sony - PlayStation 2": "PlayStation 2", "Sony - PlayStation Portable": "PSP", "Sony - PlayStation Portable (PSN)": "PSP",
    "NEC - PC Engine - TurboGrafx 16": "TurboGrafx-16", "NEC - PC Engine - TurboGrafx 16 (alt)": "PC Engine",
    "NEC - PC Engine CD - TurboGrafx-CD": "TurboGrafx-CD", "NEC - PC Engine CD - TurboGrafx-CD (alt)": "PC Engine CD",
    "NEC - PC Engine SuperGrafx": "SuperGrafx", "NEC - PC-FX": "PC-FX", "SNK - Neo Geo": "Neo Geo", "SNK - Neo Geo CD": "Neo Geo CD",
    "SNK - Neo Geo Pocket": "Neo Geo Pocket", "SNK - Neo Geo Pocket Color": "Neo Geo Pocket Color",
    "Atari - 2600": "Atari 2600", "Atari - 5200": "Atari 5200", "Atari - 7800": "Atari 7800", "Atari - Jaguar": "Jaguar",
    "Atari - Jaguar CD": "Jaguar CD", "Atari - Lynx": "Lynx", "Bandai - WonderSwan": "WonderSwan",
    "Bandai - WonderSwan Color": "WonderSwan Color", "Coleco - ColecoVision": "ColecoVision", "Commodore - 64": "Commodore 64",
    "Commodore - Amiga": "Amiga", "Commodore - Amiga CD32": "Amiga CD32", "Commodore - CDTV": "CDTV",
    "FBNeo - Arcade Games": "Arcade", "MAME 2003-Plus": "Arcade", "MAME 2010": "Arcade", "GCE - Vectrex": "Vectrex",
    "Magnavox - Odyssey": "Odyssey", "Magnavox - Odyssey2": "Odyssey 2", "Mattel - Intellivision": "Intellivision",
    "Philips - CD-i": "CD-i", "Sharp - X68000": "X68000", "Sinclair - ZX Spectrum": "ZX Spectrum",
    "The 3DO Company - 3DO": "3DO", "Fujitsu - FM Towns Marty": "FM Towns", "00 - Generic Background": "",
    "Import Content": "Import", "Main Menu": "Main Menu",
}


def label(name):
    if name in NAMES:
        return NAMES[name]
    return name.split(" - ", 1)[-1] if " - " in name else name


def rgb(h):
    h = h.lstrip("#"); return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _mask(text, font, stroke=0):
    l, t, r, b = font.getbbox(text, stroke_width=stroke)
    pad = 160
    m = Image.new("L", (r - l + pad * 2, b - t + pad * 2))
    ImageDraw.Draw(m).text((pad - l, pad - t), text, font=font, fill=255, stroke_width=stroke, stroke_fill=255)
    return m, pad


def _fit(fontfile, text, maxw, maxh):
    size = maxh
    while size > 20:
        f = ImageFont.truetype(fontfile, size)
        l, t, r, b = f.getbbox(text)
        if r - l <= maxw and b - t <= maxh:
            return f
        size -= 6
    return ImageFont.truetype(fontfile, 20)


def solid(mask, col):
    im = Image.new("RGBA", mask.size, col + (0,)); im.putalpha(mask); return im


def render(text, st, fontdir, maxw=1900, maxh=260):
    """Returns an RGBA image of the styled lettering (with padding)."""
    kind = st["kind"]
    f = _fit(str(fontdir / st["font"]), text, maxw, int(maxh * st.get("scale", 1)))
    m, pad = _mask(text, f)
    W, H = m.size
    out = Image.new("RGBA", (W, H))
    if kind == "neon":  # glass tube: coloured halo + tube + hot white core
        c = rgb(st["color"])
        for r, a in ((60, .55), (28, .8), (10, 1.0)):
            out.alpha_composite(solid(m.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(r)).point(lambda v: int(min(255, v * a * 1.6))), c))
        out.alpha_composite(solid(m, c))
        core = m.filter(ImageFilter.MinFilter(max(3, (f.size // 28) | 1))).filter(ImageFilter.GaussianBlur(2))
        out.alpha_composite(solid(core, (255, 255, 255)))
    elif kind == "chrome":  # vertical gradient + outline + glow
        c1, c2, oc = rgb(st["color"]), rgb(st["color2"]), rgb(st.get("outline", "#1a0033"))
        g = Image.linear_gradient("L").resize((W, H))
        fill = Image.composite(Image.new("RGB", (W, H), c2), Image.new("RGB", (W, H), c1), g).convert("RGBA")
        sm, _ = _mask(text, f, stroke=max(4, f.size // 22))
        out.alpha_composite(solid(sm.filter(ImageFilter.GaussianBlur(30)), rgb(st.get("glow", st["color2"]))))
        out.alpha_composite(solid(sm, oc))
        fill.putalpha(m); out.alpha_composite(fill)
        hl = Image.new("L", (W, H)); ImageDraw.Draw(hl).rectangle((0, pad, W, pad + (H - 2 * pad) * 0.45), fill=70)
        out.alpha_composite(solid(ImageChops.multiply(hl, m), (255, 255, 255)))
    elif kind == "comic":  # bold fill, thick outline, hard drop shadow, slight tilt
        c, oc = rgb(st["color"]), rgb(st.get("outline", "#000000"))
        sm, _ = _mask(text, f, stroke=max(6, f.size // 14))
        sh = Image.new("RGBA", (W, H)); sh.paste(solid(sm, (0, 0, 0)), (14, 16), solid(sm, (0, 0, 0)))
        out.alpha_composite(sh); out.alpha_composite(solid(sm, oc)); out.alpha_composite(solid(m, c))
        if "color2" in st:
            g = Image.linear_gradient("L").resize((W, H)).point(lambda v: 255 if v > 150 else 0)
            out.alpha_composite(solid(ImageChops.multiply(m, g), rgb(st["color2"])))
        out = out.rotate(st.get("tilt", 4), resample=Image.BICUBIC, expand=True)
    elif kind == "block3d":  # stacked extrusion, blocky
        c, ec = rgb(st["color"]), rgb(st["extrude"])
        depth = max(8, f.size // 9)
        for i in range(depth, 0, -1):
            lay = Image.new("RGBA", (W, H)); lay.paste(solid(m, ec), (i, i), solid(m, ec)); out.alpha_composite(lay)
        out.alpha_composite(solid(m, c))
        if "outline" in st:
            edge = ImageChops.subtract(m.filter(ImageFilter.MaxFilter(5)), m)
            out.alpha_composite(solid(edge, rgb(st["outline"])))
    elif kind == "mcblock":  # Minecraft-logo style: pixel font upscaled to blocks, stone texture, 3D drop
        import random
        small = ImageFont.truetype(str(fontdir / st["font"]), 8)
        l, t, r, b = small.getbbox(text)
        tiny = Image.new("L", (r - l + 2, b - t + 2)); ImageDraw.Draw(tiny).text((1 - l, 1 - t), text, font=small, fill=255)
        tiny = tiny.point(lambda v: 255 if v > 100 else 0)
        k = max(6, min(maxh // tiny.height, maxw // tiny.width))
        big = tiny.resize((tiny.width * k, tiny.height * k), Image.NEAREST)
        rnd = random.Random(7); tex = Image.new("RGB", tiny.size)
        base = rgb(st["color"])
        tex.putdata([tuple(max(0, min(255, c + rnd.randint(-38, 38))) for c in base) for _ in range(tiny.width * tiny.height)])
        tex = tex.resize(big.size, Image.NEAREST).convert("RGBA")
        P = 40; W2, H2 = big.width + P * 2 + k * 3, big.height + P * 2 + k * 3
        out = Image.new("RGBA", (W2, H2))
        ol = big.filter(ImageFilter.MaxFilter((k // 2) * 2 + 1))
        for i in range(k * 2, 0, -max(1, k // 4)):
            out.paste(solid(ol, (20, 20, 20)), (P + i, P + i), solid(ol, (20, 20, 20)))
        ext = rgb(st["extrude"])
        for i in range(k * 2, 0, -max(1, k // 4)):
            out.paste(solid(big, ext), (P + i, P + i), solid(big, ext))
        out.paste(solid(ol, (20, 20, 20)), (P, P), solid(ol, (20, 20, 20)))
        tex.putalpha(big); out.alpha_composite(tex, (P, P))
        hl = Image.new("L", big.size); hl.paste(big.crop((0, 0, big.width, big.height - k // 2)), (0, k // 2))
        top = ImageChops.subtract(big, hl)
        out.alpha_composite(solid(top.point(lambda v: v // 3), (255, 255, 255)), (P, P))
    elif kind == "stripes":  # 70s offset rainbow shadow
        cols = [rgb(x) for x in st["stripes"]]
        step = max(6, f.size // 16)
        for i, col in reversed(list(enumerate(cols, 1))):
            lay = Image.new("RGBA", (W, H)); lay.paste(solid(m, col), (i * step, i * step), solid(m, col)); out.alpha_composite(lay)
        out.alpha_composite(solid(m, rgb(st["color"])))
    elif kind == "stencil":  # solid colour + soft dark shadow + grit
        c = rgb(st["color"])
        out.alpha_composite(solid(m.filter(ImageFilter.GaussianBlur(10)), (0, 0, 0)))
        out.alpha_composite(solid(m, c))
        if "color2" in st:
            g = Image.linear_gradient("L").resize((W, H))
            out.alpha_composite(solid(ImageChops.multiply(m, g.point(lambda v: int(v * .8))), rgb(st["color2"])))
    bb = out.getbbox()
    return out.crop(bb) if bb else out


def place(canvas, text, st, fontdir, x=140, y=60, maxw=1900, maxh=260):
    """Draw lettering in the upper-left corner of a 3840x2160 canvas."""
    if not text:
        return canvas
    art = render(text, st, fontdir, maxw, maxh)
    if art.height > maxh + 160:
        art.thumbnail((maxw + 200, maxh + 160), Image.LANCZOS)
    canvas.alpha_composite(art, (x, y))
    return canvas
