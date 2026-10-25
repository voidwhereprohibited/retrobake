"""RetroBake ROM boot smoke test (CI entry point; exits nonzero on any failure).

For every ROM (the two self-test ROMs plus every baked ROM in --roms) and every core
for its system, boot it headless in a child process and check that it:
  1. loads and runs without crashing or hanging (child exit 0 inside the timeout),
  2. draws real frames (sane size, not an all-black screen),
  3. publishes the boot signature "RB" v1 with state title(1) or gameplay(2),
  4. reaches gameplay (state 2) after Start is pressed, and never reports error (0xEE).

Cores are the libretro builds players use in RetroArch: NES = Mesen + FCEUmm,
SNES = Snes9x. CI downloads them with --fetch-cores. Never run this on Roger's PC.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from selftest_roms import write_selftest_roms  # noqa: E402

CORES = {"nes": ["mesen", "fceumm"], "snes": ["snes9x"]}
EXT_SYSTEM = {".nes": "nes", ".sfc": "snes", ".smc": "snes"}
BUILDBOT = "https://buildbot.libretro.com/nightly/{plat}/x86_64/latest/{core}_libretro.{ext}.zip"
STATE_ERROR = 0xEE
TIMEOUT_S = 120


def core_ext() -> tuple[str, str]:
    return ("windows", "dll") if sys.platform.startswith("win") else ("linux", "so")


def core_file(cores_dir: Path, core: str) -> Path:
    return cores_dir / f"{core}_libretro.{core_ext()[1]}"


def fetch_cores(cores_dir: Path) -> None:
    plat, ext = core_ext()
    cores_dir.mkdir(parents=True, exist_ok=True)
    for core in sorted({c for cs in CORES.values() for c in cs}):
        url = BUILDBOT.format(plat=plat, core=core, ext=ext)
        with urllib.request.urlopen(url, timeout=120) as resp:  # noqa: S310 - fixed https URL
            blob = resp.read()
        name = f"{core}_libretro.{ext}"
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            data = zf.read(name)  # read the one expected member only (no zip-slip)
        core_file(cores_dir, core).write_bytes(data)
        print(f"fetched {name} sha256={hashlib.sha256(data).hexdigest()} from {url}")


def boot(core: Path, rom: Path, system: str) -> dict:
    cmd = [sys.executable, str(HERE / "libretro_harness.py"), "--core", str(core)]
    cmd += ["--rom", str(rom), "--system", system]
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            cmd, capture_output=True, text=True, timeout=TIMEOUT_S, check=False
        )
    except subprocess.TimeoutExpired:
        return {"error": f"hung: no result within {TIMEOUT_S}s"}
    lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("RESULT ")]
    if proc.returncode != 0 or not lines:
        tail = (proc.stderr or proc.stdout)[-800:]
        return {"error": f"crashed (exit {proc.returncode}): {tail}"}
    return json.loads(lines[-1][len("RESULT ") :])


def check(result: dict) -> list[str]:
    if "error" in result:
        return [result["error"]]
    if not result.get("loaded"):
        return ["core refused to load the ROM"]
    problems = []
    frame = result.get("frame", {})
    if result.get("frames_drawn", 0) < 60:
        problems.append(f"only {result.get('frames_drawn', 0)} frames drawn")
    if frame.get("width", 0) < 200 or frame.get("height", 0) < 200:
        problems.append(f"odd frame size {frame.get('width')}x{frame.get('height')}")
    if frame.get("nonblack", 0) == 0:
        problems.append("screen is completely black")
    boot_sig, after = result.get("sig_boot"), result.get("sig_after_start")
    if not boot_sig or boot_sig[:3] != [0x52, 0x42, 1]:
        problems.append(f"no boot signature 'RB' v1 in RAM (got {boot_sig})")
    else:
        if boot_sig[3] not in (1, 2):
            problems.append(f"after boot, state is {boot_sig[3]} (want 1=title or 2=gameplay)")
        if not after or after[3] != 2:
            problems.append(f"Start did not reach gameplay (state {after and after[3]})")
        if STATE_ERROR in (boot_sig[3], after and after[3]):
            problems.append("engine reported a fatal error (state 0xEE)")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    default_cores = Path(os.environ.get("RETROBAKE_CORES", HERE / ".cores"))
    ap.add_argument("--cores", type=Path, default=default_cores)
    ap.add_argument("--roms", type=Path, default=os.environ.get("RETROBAKE_SMOKE_ROMS"))
    ap.add_argument("--fetch-cores", action="store_true")
    ap.add_argument("--report", type=Path, default=HERE / "out" / "smoke-report.json")
    args = ap.parse_args(argv)

    if args.fetch_cores:
        fetch_cores(args.cores)
    with tempfile.TemporaryDirectory(prefix="rb-smoke-") as tmp:
        roms = write_selftest_roms(Path(tmp))
        if args.roms and Path(args.roms).is_dir():
            roms += sorted(p for p in Path(args.roms).rglob("*") if p.suffix.lower() in EXT_SYSTEM)
        report, failed = [], 0
        for rom in roms:
            system = EXT_SYSTEM[rom.suffix.lower()]
            for core in CORES[system]:
                path = core_file(args.cores, core)
                if not path.is_file():
                    res, problems = {}, [f"core missing: {path} (run with --fetch-cores)"]
                else:
                    res = boot(path, rom, system)
                    problems = check(res)
                failed += bool(problems)
                verdict = "PASS" if not problems else "FAIL"
                print(f"{verdict}  {rom.name:<32} {core:<8} " + ("; ".join(problems) or "ok"))
                entry = {"rom": rom.name, "core": core, "ok": not problems}
                entry.update(problems=problems, result=res)
                report.append(entry)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2))
    print(f"\n{len(report) - failed}/{len(report)} boots passed. Report: {args.report}")
    return 1 if failed or not report else 0


if __name__ == "__main__":
    sys.exit(main())
