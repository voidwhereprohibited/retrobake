"""packaging/build.py helpers (the full PyInstaller run happens in CI's package job)."""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("build", ROOT / "packaging" / "build.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


def _fake_cc65(root: Path) -> Path:
    bin_dir = root / build.PLATFORM / "bin"
    bin_dir.mkdir(parents=True)
    for tool in ("ca65", "ld65"):
        (bin_dir / f"{tool}{build.EXE}").write_bytes(b"tool")
    (root / "LICENSE").write_text("zlib license", encoding="utf-8")
    return root


def test_stage_toolchain_puts_tools_and_license_where_find_cc65_looks(tmp_path):
    out = build.stage_toolchain(_fake_cc65(tmp_path / "cc65"), tmp_path / "stage")
    assert out == tmp_path / "stage" / "toolchains" / "cc65"
    assert (out / "LICENSE").read_text(encoding="utf-8") == "zlib license"
    assert sorted(p.name for p in (out / "bin").iterdir()) == [
        f"ca65{build.EXE}",
        f"ld65{build.EXE}",
    ]


def test_stage_toolchain_without_cc65_says_how_to_get_it(tmp_path):
    with pytest.raises(build.BuildError, match="build_cc65.sh"):
        build.stage_toolchain(tmp_path / "nothing", tmp_path / "stage")


def test_fetch_refuses_a_file_with_the_wrong_hash(tmp_path, monkeypatch):
    payload = tmp_path / "payload"
    payload.write_bytes(b"not what we pinned")
    dest = tmp_path / "dl" / "tool"
    with pytest.raises(build.BuildError, match="SHA-256"):
        build.fetch(payload.as_uri(), "0" * 64, dest)
    assert not dest.exists()
    good = hashlib.sha256(b"not what we pinned").hexdigest()
    assert build.fetch(payload.as_uri(), good, dest).read_bytes() == b"not what we pinned"


def test_pyinstaller_bundles_templates_third_party_toolchain_and_license(tmp_path):
    args = build.pyinstaller_args(tmp_path / "stage", tmp_path / "work", tmp_path / "dist")
    data = [args[i + 1] for i, a in enumerate(args) if a == "--add-data"]
    dests = sorted(d.rsplit(build.os.pathsep, 1)[1] for d in data)
    assert dests == [".", "templates", "third_party", "toolchains"]
    assert "--windowed" in args and "retrobake" in args  # no console; JSON data collected


def test_appdir_layout(tmp_path):
    app = tmp_path / "RetroBake"
    app.mkdir()
    (app / "RetroBake").write_bytes(b"exe")
    appdir = build.make_appdir(app, tmp_path / "RetroBake.AppDir")
    for name in ("AppRun", "retrobake.desktop", "retrobake.png", "usr/lib/retrobake/RetroBake"):
        assert (appdir / name).is_file()
    assert "usr/lib/retrobake/RetroBake" in (appdir / "AppRun").read_text(encoding="utf-8")


def test_pins_and_installer_agree_with_the_project():
    for url, digest in (build.APPIMAGETOOL, build.APPIMAGE_RUNTIME):
        assert url.startswith("https://github.com/AppImage/") and len(digest) == 64
        assert "continuous" not in url  # a fixed release, never the moving one
    iss = (ROOT / "packaging/windows/retrobake.iss").read_text(encoding="utf-8")
    assert "RetroBake-Setup-{#AppVersion}" in iss and "PrivilegesRequired=lowest" in iss
    reqs = (ROOT / "packaging/requirements.txt").read_text(encoding="utf-8")
    assert "pyinstaller==" in reqs and "--hash=sha256:" in reqs
