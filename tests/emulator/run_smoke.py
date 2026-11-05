"""RetroBake ROM boot smoke test (CI entry point; exits nonzero on any failure).

For every ROM (the two self-test ROMs plus every baked ROM in --roms) and every core
for its system, boot it headless in a child process and check that it:
  1. loads and runs without crashing or hanging (child exit 0 inside the timeout),
  2. draws real frames (sane size, not an all-black screen),
  3. publishes the boot signature "RB" v1 with state title(1) or gameplay(2),
  4. reaches gameplay (state 2) after Start is pressed, and never reports error (0xEE).

Cores are the libretro builds players use in RetroArch: NES = Mesen + FCEUmm,
SNES = Snes9x. CI downloads them with --fetch-cores from the RetroArch stable core pack
pinned in cores.lock.json: the archive's sha256 is checked before anything is extracted,
and every core's sha256 is checked before it is loaded. Any mismatch stops the run.
Never run this on Roger's PC.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
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
LOCK = HERE / "cores.lock.json"
STATE_ERROR = 0xEE
TIMEOUT_S = 120


def core_ext() -> tuple[str, str]:
    return ("windows", "dll") if sys.platform.startswith("win") else ("linux", "so")


def core_file(cores_dir: Path, core: str) -> Path:
    return cores_dir / f"{core}_libretro.{core_ext()[1]}"


class CoreVerifyError(RuntimeError):
    """A downloaded archive or a core does not match the sha256 pinned in cores.lock.json."""


def load_lock() -> dict:
    return json.loads(LOCK.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_core(path: Path, core: str, lock: dict | None = None) -> None:
    """Refuse to go on unless `path` is the pinned build of `core` for this platform."""
    want = (lock or load_lock())["cores"][core_ext()[0]][core]["sha256"]
    got = sha256_file(path)
    if got != want:
        raise CoreVerifyError(f"{path.name}: sha256 {got} != pinned {want}; refusing to load")


def download(url: str, dest: Path) -> None:
    with urllib.request.urlopen(url, timeout=300) as resp, dest.open("wb") as out:  # noqa: S310 - pinned https URL
        shutil.copyfileobj(resp, out, 1 << 20)


def extract_member(archive: Path, member: str) -> bytes:
    seven = shutil.which("7z") or shutil.which("7za")
    if not seven:
        raise RuntimeError("7z is needed to unpack the RetroArch core pack")
    proc = subprocess.run(  # noqa: S603 - fixed argv, no shell; member names come from the lock
        [seven, "e", "-so", str(archive), member], capture_output=True, check=True
    )
    return proc.stdout


def fetch_zip_core(cores_dir: Path, core: str, pin: dict) -> None:
    """Fetch a core pinned to its own buildbot zip; both zip and core are sha256-checked."""
    with tempfile.TemporaryDirectory(prefix="rb-core-") as tmp:
        archive = Path(tmp) / "core.zip"
        download(pin["url"], archive)
        got = sha256_file(archive)
        if got != pin["zip_sha256"]:
            raise CoreVerifyError(
                f"{pin['url']}: sha256 {got} != pinned {pin['zip_sha256']}; refusing to extract"
            )
        with zipfile.ZipFile(archive) as zf:
            data = zf.read(pin["member"])
    if hashlib.sha256(data).hexdigest() != pin["sha256"]:
        raise CoreVerifyError(f"{pin['member']} in {pin['url']} is not the pinned build")
    core_file(cores_dir, core).write_bytes(data)
    print(f"fetched {pin['member']} sha256={pin['sha256']} ({pin['version']}, {pin['built']})")


def fetch_cores(cores_dir: Path) -> None:
    plat, ext = core_ext()
    lock = load_lock()
    wanted = sorted({c for cs in CORES.values() for c in cs})
    cores_dir.mkdir(parents=True, exist_ok=True)
    missing = []
    for core in wanted:
        path = core_file(cores_dir, core)
        try:
            if path.is_file():
                verify_core(path, core, lock)
                continue
        except CoreVerifyError:
            path.unlink()
        missing.append(core)
    if not missing:
        print(f"pinned cores already present in {cores_dir}")
        return
    for core in [c for c in missing if "zip_sha256" in lock["cores"][plat][c]]:
        fetch_zip_core(cores_dir, core, lock["cores"][plat][core])
        missing.remove(core)
    if not missing:
        return
    pack = lock["archives"][plat]
    with tempfile.TemporaryDirectory(prefix="rb-cores-") as tmp:
        archive = Path(tmp) / "cores.7z"
        download(pack["url"], archive)
        got = sha256_file(archive)
        if got != pack["sha256"]:
            raise CoreVerifyError(
                f"{pack['url']}: sha256 {got} != pinned {pack['sha256']}; refusing to extract"
            )
        for core in missing:
            data = extract_member(archive, lock["cores"][plat][core]["member"])
            want = lock["cores"][plat][core]["sha256"]
            if hashlib.sha256(data).hexdigest() != want:
                raise CoreVerifyError(f"{core}_libretro.{ext} in the pack is not the pinned build")
            core_file(cores_dir, core).write_bytes(data)
            print(f"fetched {core}_libretro.{ext} sha256={want} (RetroArch {lock['release']})")


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
    ap.add_argument(
        "--verify-cores", action="store_true", help="only check the pinned cores, then exit"
    )
    ap.add_argument(
        "--allow-unpinned",
        action="store_true",
        help="local use only: boot cores that do not match cores.lock.json",
    )
    ap.add_argument("--report", type=Path, default=HERE / "out" / "smoke-report.json")
    args = ap.parse_args(argv)

    try:
        if args.fetch_cores:
            fetch_cores(args.cores)
        if args.verify_cores:
            for core in sorted({c for cs in CORES.values() for c in cs}):
                verify_core(core_file(args.cores, core), core)
            print("pinned cores verified")
            return 0
    except (CoreVerifyError, FileNotFoundError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
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
                    try:
                        if not args.allow_unpinned:
                            verify_core(path, core)
                        res = boot(path, rom, system)
                        problems = check(res)
                    except CoreVerifyError as exc:
                        res, problems = {}, [str(exc)]
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
