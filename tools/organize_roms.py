#!/usr/bin/env python3
"""Organize Roger's ROMs from ~/Downloads into ~/ROMs/<RetroArch system name>/ with clean titles,
keep one best copy per title, and write RetroArch playlists named like the systems (so dynamic
wallpapers match). Originals in multi-file archives are left untouched in Downloads."""
import json, os, re, shutil, subprocess, tempfile, zipfile
from pathlib import Path

HOME = Path.home(); DL = HOME / "Downloads"; ROMS = HOME / "ROMs"
PL = HOME / ".local/share/retroarch/plists"
Z7 = HOME / "Projects/retrobake/.tools/7z/7zz"
NES, SNES, MD, X32, NDS, LYNX = ("Nintendo - Nintendo Entertainment System", "Nintendo - Super Nintendo Entertainment System",
                                 "Sega - Mega Drive - Genesis", "Sega - 32X", "Nintendo - Nintendo DS", "Atari - Lynx")
BAD = re.compile(r"\[(b|h|c|t|o|f|a|p|T[+-]?)[^\]]*\]|\((pre-release|beta|proto|hack|pd|sample|demo)[^)]*\)", re.I)
REGION_RANK = [("(u)", 0), ("(usa)", 0), ("(ju)", 1), ("(ue)", 1), ("(uj)", 1), ("(w)", 1), ("(jue)", 1), ("(world)", 1),
               ("(e)", 2), ("(europe)", 2), ("(j)", 3), ("(japan)", 3)]


def clean(name):
    s = re.sub(r"^\d{3,4}\s*-\s*", "", name)
    s = re.sub(r"\s*[\(\[][^\)\]]*[\)\]]", "", s)
    s = re.sub(r"\s+", " ", s).strip(" -_.")
    m = re.match(r"^(.*), (The|A|An)$", s)
    if m:
        s = f"{m.group(2)} {m.group(1)}"
    return s.replace("/", "-")


def rank(name):
    n = name.lower()
    r = next((v for k, v in REGION_RANK if k in n), 4)
    return (0 if "[!]" in n else 1, r, len(n))


def pick_best(names):
    best = {}
    for n in names:
        base = os.path.basename(n)
        if BAD.search(base):
            continue
        t = clean(os.path.splitext(base)[0]).lower()
        if t not in best or rank(base) < rank(os.path.basename(best[t])):
            best[t] = n
    return list(best.values())


def place(src, system, move):
    d = ROMS / system; d.mkdir(parents=True, exist_ok=True)
    stem, ext = os.path.splitext(src.name)
    dst = d / f"{clean(stem)}{ext.lower()}"
    i = 2
    while dst.exists():
        dst = d / f"{clean(stem)} ({i}){ext.lower()}"; i += 1
    (shutil.move if move else shutil.copy2)(str(src), str(dst))
    return dst


def main():
    log = {}
    # NES / SNES folders + loose SNES zips: move + rename (zips kept as-is, RetroArch reads them)
    for folder, system in (("Nintendo", NES), ("Super Nintendo", SNES)):
        files = sorted((DL / folder).glob("*.zip")) if (DL / folder).exists() else []
        for f in [DL / folder / os.path.basename(n) for n in pick_best([str(x) for x in files])]:
            place(f, system, True)
        log[system] = len(files)
    for f in ["Aladdin.zip", "BS Mario Collection 3 (J).zip", "Earthworm Jim.zip", "Super Mario World (U) [!].zip", "Zombies Ate My Neighbors.zip"]:
        if (DL / f).exists():
            place(DL / f, SNES, True)
    # Nintendo DS pack: extract the .nds out of each zip (drops the ad .url files)
    nds = DL / "Progetto Nintendo DS roms - pack 010"
    if nds.exists():
        zips = sorted(nds.glob("*.zip"))
        for z in [Path(p) for p in pick_best([str(x) for x in zips])]:
            with zipfile.ZipFile(z) as zf, tempfile.TemporaryDirectory() as t:
                inner = next(n for n in zf.namelist() if n.lower().endswith(".nds"))
                zf.extract(inner, t); src = Path(t) / inner
                place(src.rename(Path(t) / (z.stem + ".nds")), NDS, True)
        log[NDS] = len(zips)
    # Mega Drive GoodGen set (solid multi-volume RAR): extract one best copy per title
    mdr = DL / "MEGADRIVE_ROMS_FULL_COLLECTION/MEGADRIVE_ROMS_FULL_COLLECTION.part01.rar"
    if mdr.exists():
        out = subprocess.run([str(Z7), "l", "-ba", "-slt", str(mdr)], capture_output=True, text=True).stdout
        names = [l[7:] for l in out.splitlines() if l.startswith("Path = ") and l.lower().endswith(".zip")]
        chosen = pick_best(names)
        with tempfile.TemporaryDirectory(dir=HOME) as t:
            lst = Path(t) / "list.txt"; lst.write_text("\n".join(chosen))
            subprocess.run([str(Z7), "x", "-y", f"-o{t}/x", str(mdr), f"@{lst}"], check=True, stdout=subprocess.DEVNULL)
            for n in chosen:
                p = Path(t) / "x" / n
                if p.exists():
                    place(p, X32 if "32x" in p.name.lower() else MD, True)
        log[MD] = len(names)
    # Atari Lynx: main set only (skip bad dumps / overdumps)
    lyr = DL / "LynxRen/LynxRen.rar"
    if lyr.exists():
        with tempfile.TemporaryDirectory(dir=HOME) as t:
            subprocess.run([str(Z7), "x", "-y", f"-o{t}", str(lyr)], check=True, stdout=subprocess.DEVNULL)
            files = [str(p) for p in Path(t).rglob("*.lnx")]
            for p in pick_best(files):
                place(Path(p), LYNX, True)
    # Playlists named exactly like the systems
    PL.mkdir(parents=True, exist_ok=True)
    for d in sorted(p for p in ROMS.iterdir() if p.is_dir()):
        items = []
        for f in sorted(d.iterdir(), key=lambda p: p.name.lower()):
            path = str(f)
            if f.suffix == ".zip":
                with zipfile.ZipFile(f) as zf:
                    inner = [n for n in zf.namelist() if not n.endswith((".url", ".txt", ".nfo"))]
                if inner:
                    path = f"{f}#{inner[0]}"
            items.append({"path": path, "label": f.stem, "core_path": "DETECT", "core_name": "DETECT",
                          "crc32": "DETECT", "db_name": f"{d.name}.lpl"})
        pl = {"version": "1.5", "default_core_path": "", "default_core_name": "", "label_display_mode": 0,
              "right_thumbnail_mode": 0, "left_thumbnail_mode": 0, "sort_mode": 0, "items": items}
        (PL / f"{d.name}.lpl").write_text(json.dumps(pl, indent=2))
        print(f"{len(items):5}  {d.name}")


if __name__ == "__main__":
    main()
