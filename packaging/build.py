"""Build RetroBake's release bundles.

    python packaging/build.py [--version 0.1.0] [--out dist]

Windows: PyInstaller folder -> Inno Setup installer (RetroBake-Setup-<version>.exe).
Linux:   PyInstaller folder -> AppImage (RetroBake-<version>-x86_64.AppImage).

Needs `pip install --require-hashes -r packaging/requirements.txt` and the bundled cc65 in
toolchains/cc65 (tools/build_cc65.sh). Downloads (appimagetool and the AppImage runtime) are
pinned by SHA-256 and refused if they don't match. Writes SHA256SUMS next to the result.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tomllib
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "packaging"
WINDOWS = sys.platform == "win32"
PLATFORM = "windows" if WINDOWS else "linux"
EXE = ".exe" if WINDOWS else ""

# Pinned AppImage tools (x86_64). SHA-256s match the digests GitHub publishes for the assets.
APPIMAGETOOL = (
    "https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage",
    "ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0",
)
APPIMAGE_RUNTIME = (
    "https://github.com/AppImage/type2-runtime/releases/download/20251108/runtime-x86_64",
    "2fca8b443c92510f1483a883f60061ad09b46b978b2631c807cd873a47ec260d",
)


class BuildError(Exception):
    pass


def project_version() -> str:
    with open(ROOT / "pyproject.toml", "rb") as f:
        return tomllib.load(f)["project"]["version"]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def fetch(url: str, expected: str, dest: Path) -> Path:
    """Download `url` to `dest` (reusing a cached copy) and check its SHA-256."""
    if not dest.is_file() or sha256(dest) != expected:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=60) as r, open(dest, "wb") as f:  # noqa: S310
            shutil.copyfileobj(r, f)
    if sha256(dest) != expected:
        dest.unlink()
        raise BuildError(f"{dest.name}: SHA-256 doesn't match the pinned value; refusing it")
    return dest


def stage_toolchain(cc65: Path, stage: Path) -> Path:
    """Copy this platform's ca65/ld65 and cc65's LICENSE to stage/toolchains/cc65."""
    bin_dir = cc65 / PLATFORM / "bin"
    tools = [bin_dir / f"{t}{EXE}" for t in ("ca65", "ld65")]
    missing = [str(t) for t in tools + [cc65 / "LICENSE"] if not t.is_file()]
    if missing:
        raise BuildError("bundled cc65 is missing (run tools/build_cc65.sh): " + ", ".join(missing))
    out = stage / "toolchains" / "cc65"
    shutil.rmtree(out, ignore_errors=True)
    (out / "bin").mkdir(parents=True)
    for tool in tools:
        shutil.copy2(tool, out / "bin" / tool.name)
    shutil.copy2(cc65 / "LICENSE", out / "LICENSE")
    return out


def pyinstaller_args(stage: Path, work: Path, dist: Path) -> list[str]:
    def data(src: Path, dest: str) -> list[str]:
        return ["--add-data", f"{src}{os.pathsep}{dest}"]

    return [
        sys.executable, "-m", "PyInstaller", str(HERE / "launcher.py"),
        "--name", "RetroBake", "--windowed", "--noconfirm", "--clean",
        *(["--icon", str(HERE / "retrobake.ico")] if WINDOWS else []),  # AppDir has the PNG
        "--workpath", str(work), "--distpath", str(dist), "--specpath", str(work),
        "--collect-data", "retrobake",
        "--exclude-module", "tkinter", "--exclude-module", "PIL",
        *data(ROOT / "templates", "templates"),
        *data(ROOT / "third_party", "third_party"),
        *data(stage / "toolchains", "toolchains"),
        *data(ROOT / "LICENSE", "."),
    ]  # fmt: skip


def freeze(cc65: Path, build: Path) -> Path:
    stage_toolchain(cc65, build / "stage")
    dist = build / "pyinstaller"
    run(pyinstaller_args(build / "stage", build / "work", dist))
    return dist / "RetroBake"


def windows_installer(app: Path, version: str, out: Path) -> Path:
    iscc = shutil.which("iscc") or r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    if not Path(iscc).is_file():
        raise BuildError("Inno Setup 6 (iscc) not found")
    run([iscc, f"/DAppVersion={version}", f"/DSourceDir={app}", f"/DOutDir={out}",
         str(HERE / "windows" / "retrobake.iss")])  # fmt: skip
    return out / f"RetroBake-Setup-{version}.exe"


def make_appdir(app: Path, appdir: Path) -> Path:
    shutil.rmtree(appdir, ignore_errors=True)
    shutil.copytree(app, appdir / "usr" / "lib" / "retrobake", symlinks=True)
    shutil.copy2(HERE / "linux" / "AppRun", appdir / "AppRun")
    (appdir / "AppRun").chmod(0o755)
    shutil.copy2(HERE / "linux" / "retrobake.desktop", appdir / "retrobake.desktop")
    shutil.copy2(HERE / "retrobake.png", appdir / "retrobake.png")
    return appdir


def appimage(app: Path, version: str, out: Path, build: Path) -> Path:
    tool = fetch(*APPIMAGETOOL, build / "downloads" / "appimagetool-1.9.1-x86_64.AppImage")
    runtime = fetch(*APPIMAGE_RUNTIME, build / "downloads" / "runtime-x86_64-20251108")
    tool.chmod(0o755)
    appdir = make_appdir(app, build / "RetroBake.AppDir")
    target = out / f"RetroBake-{version}-x86_64.AppImage"
    # Extract-and-run: works without FUSE (CI runners, containers).
    env = {**os.environ, "ARCH": "x86_64", "APPIMAGE_EXTRACT_AND_RUN": "1"}
    run([tool, "--no-appstream", "--runtime-file", runtime, appdir, target], env=env)
    return target


def write_checksums(files: list[Path], out: Path) -> Path:
    sums = out / "SHA256SUMS"
    sums.write_text("".join(f"{sha256(f)}  {f.name}\n" for f in files), encoding="utf-8")
    return sums


def run(argv: list, env: dict | None = None) -> None:
    print("+", " ".join(str(a) for a in argv), flush=True)
    subprocess.run([str(a) for a in argv], check=True, env=env)  # noqa: S603 - fixed tools


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--version", default=project_version())
    ap.add_argument("--out", type=Path, default=ROOT / "dist")
    ap.add_argument("--cc65", type=Path, default=ROOT / "toolchains" / "cc65")
    ap.add_argument("--build", type=Path, default=ROOT / "build" / "package")
    args = ap.parse_args(argv)
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    try:
        app = freeze(args.cc65.resolve(), args.build.resolve())
        if WINDOWS:
            result = windows_installer(app, args.version, out)
        else:
            result = appimage(app, args.version, out, args.build.resolve())
    except (BuildError, subprocess.CalledProcessError) as e:
        print(f"packaging failed: {e}", file=sys.stderr)
        return 1
    print(write_checksums([result], out).read_text(encoding="utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
