#!/usr/bin/env python3
"""Convert Yoshi's TV Game Icons (32x32 .ico pixel art) to XMB system icon names, upscaled 7x nearest-neighbour.
Usage: map_yoshi.py <ico dir> <out dir>"""
import sys
from pathlib import Path
from PIL import Image

MAP = {
    "Nes": ["Nintendo - Nintendo Entertainment System"], "Fc_01": ["Nintendo - Family Computer"],
    "Fc_DiskSystem01": ["Nintendo - Family Computer Disk System"], "Snes": ["Nintendo - Super Nintendo Entertainment System"],
    "Sfc": ["Nintendo - Super Famicom"], "N64": ["Nintendo - Nintendo 64"], "N64Dd01": ["Nintendo - Nintendo 64DD"],
    "Ngc_Violet01": ["Nintendo - GameCube"], "Gameboy01": ["Nintendo - Game Boy"], "GBC_Purple": ["Nintendo - Game Boy Color"],
    "Gba01": ["Nintendo - Game Boy Advance"], "NintendoDS_01": ["Nintendo - Nintendo DS"], "Nintendo3DS_b01": ["Nintendo - Nintendo 3DS"],
    "VirtualBoy": ["Nintendo - Virtual Boy"], "Wii": ["Nintendo - Wii"], "PokemonMini_Blue01": ["Nintendo - Pokemon Mini"],
    "Gaw": ["Handheld Electronic Game"], "Sfc_SuperGB01": ["Nintendo - Super Game Boy"], "Sfc_satell01": ["Nintendo - Satellaview"],
    "Genesis": ["Sega - Mega Drive - Genesis"], "Sms": ["Sega - Master System - Mark III"], "GameGear01": ["Sega - Game Gear"],
    "MegaCd01": ["Sega - Mega-CD - Sega CD"], "MD_Super32X01": ["Sega - 32X"], "Ss": ["Sega - Saturn"], "DC01": ["Sega - Dreamcast"],
    "Sg-1000": ["Sega - SG-1000"], "Psx_01": ["Sony - PlayStation"], "Ps2": ["Sony - PlayStation 2"], "Psp_01": ["Sony - PlayStation Portable"],
    "TurboGrafx01": ["NEC - PC Engine - TurboGrafx 16"], "TurboGrafx01CD": ["NEC - PC Engine CD - TurboGrafx-CD"],
    "Pce_SuperGrafx01": ["NEC - PC Engine SuperGrafx"], "PcFx01": ["NEC - PC-FX"], "NeoGeo01": ["SNK - Neo Geo"],
    "NeoGeoCd": ["SNK - Neo Geo CD"], "NeoGeoPocket": ["SNK - Neo Geo Pocket"], "NeoGeoPocket_c": ["SNK - Neo Geo Pocket Color"],
    "Atari2600": ["Atari - 2600"], "Jaguar01": ["Atari - Jaguar"], "JaguarCd": ["Atari - Jaguar CD"], "Lynx": ["Atari - Lynx"],
    "WonderSwan_01": ["Bandai - WonderSwan"], "WSColor01": ["Bandai - WonderSwan Color"], "3DO_Real": ["The 3DO Company - 3DO"],
    "AmigaCd32": ["Commodore - Amiga CD32"], "Odyssey01": ["Magnavox - Odyssey2"], "FmMarty": ["Fujitsu - FM Towns Marty"],
    "Arcade_Astrocity": ["MAME", "MAME 2003-Plus", "MAME 2010", "FBNeo - Arcade Games"], "Xbox01": ["Microsoft - Xbox"],
    "Playdia01": ["Bandai - Playdia"], "LaserActive": ["Pioneer - LaserActive"], "Casettevision": ["Epoch - Cassette Vision"],
}


def main():
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    n = 0
    for code, names in MAP.items():
        f = src / f"{code}.ico"
        if not f.exists():
            print("missing", code); continue
        im = Image.open(f).convert("RGBA")
        bb = im.getbbox(); im = im.crop(bb) if bb else im
        s = max(1, 224 // max(im.size))
        im = im.resize((im.width * s, im.height * s), Image.NEAREST)
        c = Image.new("RGBA", (256, 256)); c.paste(im, ((256 - im.width) // 2, (256 - im.height) // 2), im)
        for nm in names:
            c.save(out / f"{nm}.png"); c.save(out / f"{nm}-content.png"); n += 2
    print(n, "icons ->", out)


if __name__ == "__main__":
    main()
