import sys
from pathlib import Path

import pytest

from retrobake.security import BuildLimits, BuildWorkspace, SandboxError, run_build

PY = Path(sys.executable).resolve()
TOOLS = [PY.parent]


def _py(code):
    return [PY, "-I", "-c", code]


def test_workspace_lifecycle(tmp_path):
    tpl = tmp_path / "templates" / "hello"
    tpl.mkdir(parents=True)
    (tpl / "main.s").write_text("; template\n")
    with BuildWorkspace([tmp_path / "templates"]) as ws:
        root = ws.root
        ws.copy_template(tpl, "src")
        assert (root / "src" / "main.s").read_text() == "; template\n"
        ws.write_file("data/level.bin", b"\x01\x02")
        assert ws.read_output("data/level.bin") == b"\x01\x02"
        with pytest.raises(SandboxError):
            ws.write_file("../escape.txt", "x")
        with pytest.raises(SandboxError):
            ws.copy_template(tmp_path, "x")  # not an approved template root child
        with pytest.raises(SandboxError):
            ws.read_output("missing.nes")
    assert not root.exists()


def test_rejects_program_outside_toolchain(tmp_path):
    with BuildWorkspace([tmp_path]) as ws, pytest.raises(SandboxError):
        run_build(_py("print(1)"), workspace=ws, toolchain_dirs=[tmp_path])


def test_runs_tool_with_clean_env(tmp_path, monkeypatch):
    monkeypatch.setenv("RETROBAKE_SECRET", "leak")
    code = (
        "import os,pathlib;"
        "pathlib.Path('out.nes').write_bytes(b'NES\\x1a');"
        "print(os.environ.get('RETROBAKE_SECRET','none'), os.environ['https_proxy'])"
    )
    with BuildWorkspace([tmp_path]) as ws:
        res = run_build(_py(code), workspace=ws, toolchain_dirs=TOOLS)
        assert res.ok, res.stderr
        assert res.stdout.split() == ["none", "http://127.0.0.1:9"]
        assert ws.read_output("out.nes") == b"NES\x1a"


def test_timeout_kills_build(tmp_path):
    limits = BuildLimits(timeout_s=2)
    with BuildWorkspace([tmp_path], limits) as ws, pytest.raises(SandboxError):
        run_build(_py("import time; time.sleep(60)"), workspace=ws, toolchain_dirs=TOOLS)


def test_output_is_capped(tmp_path):
    limits = BuildLimits(max_output_bytes=100)
    with BuildWorkspace([tmp_path], limits) as ws:
        res = run_build(_py("print('x' * 100000)"), workspace=ws, toolchain_dirs=TOOLS)
        assert len(res.stdout) < 200 and res.stdout.endswith("[output trimmed]")


def test_network_blocked_when_supported(tmp_path):
    code = (
        "import socket,sys\n"
        "try:\n socket.create_connection(('1.1.1.1', 443), timeout=3); sys.exit(1)\n"
        "except OSError: sys.exit(0)\n"
    )
    with BuildWorkspace([tmp_path]) as ws:
        res = run_build(_py(code), workspace=ws, toolchain_dirs=TOOLS)
        if not res.network_isolated:
            pytest.skip("this OS does not allow a private network namespace")
        assert res.ok
