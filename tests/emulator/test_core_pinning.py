"""The emulator cores are pinned: a wrong archive or core is refused before it is used."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import run_smoke
from run_smoke import CoreVerifyError, core_ext, core_file, fetch_cores, verify_core


def test_lock_pins_fixed_https_release_builds():
    lock = run_smoke.load_lock()
    for pack in lock["archives"].values():
        assert pack["url"].startswith("https://buildbot.libretro.com/stable/1.22.2/")
        assert "nightly" not in pack["url"] and "latest" not in pack["url"]
        assert len(pack["sha256"]) == 64
    wanted = {c for cs in run_smoke.CORES.values() for c in cs}
    for plat in ("linux", "windows"):
        assert set(lock["cores"][plat]) == wanted
        assert all(len(c["sha256"]) == 64 for c in lock["cores"][plat].values())


def _fake_lock(tmp_path: Path, archive_sha: str, core_sha: str) -> Path:
    plat = core_ext()[0]
    cores = {c: {"member": f"cores/{c}", "sha256": core_sha} for c in ("fceumm", "mesen", "snes9x")}
    lock = {
        "release": "test",
        "archives": {plat: {"url": "https://example.invalid/cores.7z", "sha256": archive_sha}},
        "cores": {plat: cores},
    }
    path = tmp_path / "cores.lock.json"
    path.write_text(json.dumps(lock))
    return path


def test_archive_mismatch_is_refused_before_extracting(tmp_path, monkeypatch):
    monkeypatch.setattr(run_smoke, "LOCK", _fake_lock(tmp_path, "0" * 64, "0" * 64))
    monkeypatch.setattr(run_smoke, "download", lambda url, dest: dest.write_bytes(b"evil"))

    def never(*_a):
        raise AssertionError("extracted an archive that failed its sha256 check")

    monkeypatch.setattr(run_smoke, "extract_member", never)
    with pytest.raises(CoreVerifyError, match="refusing to extract"):
        fetch_cores(tmp_path / "cores")
    assert not list((tmp_path / "cores").iterdir())


def test_core_mismatch_inside_a_good_archive_is_refused(tmp_path, monkeypatch):
    blob = b"pack"
    sha = hashlib.sha256(blob).hexdigest()
    monkeypatch.setattr(run_smoke, "LOCK", _fake_lock(tmp_path, sha, "1" * 64))
    monkeypatch.setattr(run_smoke, "download", lambda url, dest: dest.write_bytes(blob))
    monkeypatch.setattr(run_smoke, "extract_member", lambda archive, member: b"other core")
    with pytest.raises(CoreVerifyError, match="not the pinned build"):
        fetch_cores(tmp_path / "cores")
    assert not list((tmp_path / "cores").iterdir())


def test_tampered_core_on_disk_is_never_loaded(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(run_smoke, "LOCK", _fake_lock(tmp_path, "0" * 64, "2" * 64))
    cores = tmp_path / "cores"
    cores.mkdir()
    for core in ("fceumm", "mesen", "snes9x"):
        core_file(cores, core).write_bytes(b"tampered")

    def never(*_a):
        raise AssertionError("booted a core that failed its sha256 check")

    monkeypatch.setattr(run_smoke, "boot", never)
    with pytest.raises(CoreVerifyError, match="refusing to load"):
        verify_core(core_file(cores, "fceumm"), "fceumm")
    assert run_smoke.main(["--cores", str(cores), "--verify-cores"]) == 2
    report = tmp_path / "report.json"
    assert run_smoke.main(["--cores", str(cores), "--report", str(report)]) == 1
    assert all("refusing to load" in e["problems"][0] for e in json.loads(report.read_text()))
