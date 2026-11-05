#!/usr/bin/env python3
"""Convert retro-game-console-icons (TrimUI 600w, CC BY 4.0) to RetroArch XMB system icon names.
Writes <out>/<XMB name>.png and <XMB name>-content.png at 256x256 RGBA.
Usage: map_rgci.py <series_trimui/600w@2x dir> <out dir>"""
import sys
from pathlib import Path
from PIL import Image

MAP = {
    "FC": ["Nintendo - Nintendo Entertainment System", "Nintendo - Family Computer"],
    "FDS": ["Nintendo - Family Computer Disk System"],
    "SFC": ["Nintendo - Super Nintendo Entertainment System", "Nintendo - Super Famicom"],
    "SATELLAVIEW": ["Nintendo - Satellaview"], "SUFAMI": ["Nintendo - Sufami Turbo"],
    "N64": ["Nintendo - Nintendo 64"], "N64DD": ["Nintendo - Nintendo 64DD"],
    "NGC": ["Nintendo - GameCube"], "GB": ["Nintendo - Game Boy"], "GBC": ["Nintendo - Game Boy Color"],
    "GBA": ["Nintendo - Game Boy Advance"], "NDS": ["Nintendo - Nintendo DS"], "VB": ["Nintendo - Virtual Boy"],
    "POKEMINI": ["Nintendo - Pokemon Mini"], "GW": ["Handheld Electronic Game"], "SGB": ["Nintendo - Super Game Boy"],
    "MD": ["Sega - Mega Drive - Genesis"], "MS": ["Sega - Master System - Mark III"], "GG": ["Sega - Game Gear"],
    "SEGACD": ["Sega - Mega-CD - Sega CD"], "SEGA32X": ["Sega - 32X"], "SATURN": ["Sega - Saturn"],
    "DC": ["Sega - Dreamcast"], "SG1000": ["Sega - SG-1000"], "PICO": ["Sega - PICO"], "NAOMI": ["Sega - Naomi"],
    "PS": ["Sony - PlayStation"], "PSP": ["Sony - PlayStation Portable"],
    "PCE": ["NEC - PC Engine - TurboGrafx 16"], "PCECD": ["NEC - PC Engine CD - TurboGrafx-CD"],
    "SFX": ["NEC - PC Engine SuperGrafx"], "PCFX": ["NEC - PC-FX"], "PC88": ["NEC - PC-8001 - PC-8801"], "PC98": ["NEC - PC-98"],
    "NEOGEO": ["SNK - Neo Geo"], "NEOCD": ["SNK - Neo Geo CD"], "NGP": ["SNK - Neo Geo Pocket", "SNK - Neo Geo Pocket Color"],
    "ATARI2600": ["Atari - 2600"], "ATARI5200": ["Atari - 5200"], "ATARI7800": ["Atari - 7800"], "LYNX": ["Atari - Lynx"],
    "ATARIST": ["Atari - ST"], "ATARI800": ["Atari - 8-bit"],
    "WS": ["Bandai - WonderSwan"], "WSC": ["Bandai - WonderSwan Color"], "COLECO": ["Coleco - ColecoVision"],
    "INTELLIVISION": ["Mattel - Intellivision"], "VECTREX": ["GCE - Vectrex"], "CHANNELF": ["Fairchild - Channel F"],
    "VIDEOPAC": ["Magnavox - Odyssey2"], "C64": ["Commodore - 64"], "AMIGA": ["Commodore - Amiga"],
    "AMIGACD": ["Commodore - Amiga CD32"], "AMIGACDTV": ["Commodore - CDTV"], "MSX": ["Microsoft - MSX"], "MSX2": ["Microsoft - MSX2"],
    "ZXS": ["Sinclair - ZX Spectrum"], "CPC": ["Amstrad - CPC"], "X68000": ["Sharp - X68000"], "PANASONIC": ["The 3DO Company - 3DO"],
    "MAME": ["MAME"], "MAME2003PLUS": ["MAME 2003-Plus"], "MAME2010": ["MAME 2010"], "FBNEO": ["FBNeo - Arcade Games"],
    "CPS1": ["Capcom - CP System I"], "CPS2": ["Capcom - CP System II"], "CPS3": ["Capcom - CP System III"],
    "DOS": ["DOS"], "SCUMMVM": ["ScummVM"], "DOOM": ["DOOM"], "SUPERVISION": ["Watara - Supervision"],
    "MEGADUCK": ["Mega Duck"], "ARDUBOY": ["Arduboy Inc - Arduboy"], "TIC": ["TIC-80"], "UZEBOX": ["Uzebox"],
    "VMAC": ["Apple - Macintosh"], "CHAILOVE": ["ChaiLove"], "LUTRO": ["Lutro"],
}


def main():
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    n = 0
    for code, names in MAP.items():
        f = src / f"{code}.png"
        if not f.exists():
            continue
        im = Image.open(f).convert("RGBA")
        bb = im.getbbox(); im = im.crop(bb) if bb else im
        im.thumbnail((240, 240), Image.LANCZOS)
        c = Image.new("RGBA", (256, 256)); c.paste(im, ((256 - im.width) // 2, (256 - im.height) // 2), im)
        for nm in names:
            c.save(out / f"{nm}.png"); c.save(out / f"{nm}-content.png"); n += 2
    print(n, "icons ->", out)


if __name__ == "__main__":
    main()
