"""Build sandbox for the NES/SNES bakers.

Rules (every builder must follow them):
1. Build inside a ``BuildWorkspace``: a private temp folder, removed afterwards.
2. Copy in only our engine templates (``copy_template``) and data files we generate
   (``write_file``). User text reaches the build only as cleaned data inside those files,
   never as a command-line argument and never as raw assembly.
3. Run tools only with ``run_build``: argument list (no shell), program must live inside a
   bundled toolchain folder, tiny clean environment, time/memory/file-size/process limits,
   whole process tree killed on timeout, output captured to capped temp files.
4. Network: on Linux the build runs in an empty network namespace when the system allows
   it; everywhere, proxies point at a dead address. The bundled toolchains (cc65,
   PVSnesLib/wla-dx/816-tcc) have no network code, which is the real guarantee.
5. Read results back with ``read_output`` (size-capped). Never trust file names from tools.
"""

from __future__ import annotations

import os
import shutil
import signal
import stat
import subprocess  # noqa: S404 - argument lists only, shell=False
import sys
import tempfile
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .errors import SandboxError
from .sanitizer import safe_join

_IS_WIN = sys.platform == "win32"
_DEAD_PROXY = "http://127.0.0.1:9"


@dataclass(frozen=True)
class BuildLimits:
    timeout_s: float = 120.0
    memory_bytes: int = 1024 * 1024 * 1024
    max_file_bytes: int = 16 * 1024 * 1024
    max_workspace_bytes: int = 128 * 1024 * 1024
    max_output_bytes: int = 256 * 1024
    max_processes: int = 32


@dataclass(frozen=True)
class BuildResult:
    returncode: int
    stdout: str
    stderr: str
    seconds: float
    network_isolated: bool

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def _tree_size(root: Path) -> int:
    total = 0
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            try:
                total += os.lstat(os.path.join(dirpath, name)).st_size
            except OSError:
                pass
    return total


class BuildWorkspace:
    """Private temp folder for one bake. Use as ``with BuildWorkspace(roots) as ws:``."""

    def __init__(self, template_roots: list[str | Path], limits: BuildLimits | None = None):
        self.template_roots = [Path(r).resolve() for r in template_roots]
        self.limits = limits or BuildLimits()
        self.root: Path | None = None

    def __enter__(self) -> BuildWorkspace:
        self.root = Path(tempfile.mkdtemp(prefix="retrobake-build-")).resolve()
        os.chmod(self.root, 0o700)
        return self

    def __exit__(self, *exc: object) -> None:
        self.cleanup()

    def cleanup(self) -> None:
        if self.root and self.root.exists():

            def _retry(func, path, _exc):  # read-only files on Windows
                os.chmod(path, stat.S_IWRITE)
                func(path)

            shutil.rmtree(self.root, onexc=_retry)
        self.root = None

    def _need_root(self) -> Path:
        if self.root is None:
            raise SandboxError("workspace is not open")
        return self.root

    def path(self, *parts: str) -> Path:
        return safe_join(self._need_root(), *parts)

    def copy_template(self, src: str | Path, dest: str = ".") -> Path:
        """Copy a template folder (from an approved template root) into the workspace."""
        src_path = Path(src).resolve()
        if not any(src_path == r or r in src_path.parents for r in self.template_roots):
            raise SandboxError(f"not an approved template: {src_path}")
        target = self.path(dest)
        for dirpath, dirs, files in os.walk(src_path):
            here = Path(dirpath)
            for name in dirs + files:
                if (here / name).is_symlink():
                    raise SandboxError(f"templates may not contain links: {here / name}")
            out_dir = safe_join(target, str(here.relative_to(src_path)))
            out_dir.mkdir(parents=True, exist_ok=True)
            for name in files:
                shutil.copyfile(here / name, out_dir / name)
        self._check_size()
        return target

    def write_file(self, rel: str, data: bytes | str) -> Path:
        """Write generated data (never user-chosen file names) into the workspace."""
        raw = data.encode("utf-8") if isinstance(data, str) else bytes(data)
        if len(raw) > self.limits.max_file_bytes:
            raise SandboxError(f"{rel} is too big")
        target = self.path(rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        self._check_size()
        return target

    def read_output(self, rel: str, max_bytes: int | None = None) -> bytes:
        target = self.path(rel)
        if target.is_symlink() or not target.is_file():
            raise SandboxError(f"build did not produce {rel}")
        cap = max_bytes or self.limits.max_file_bytes
        if target.stat().st_size > cap:
            raise SandboxError(f"{rel} is larger than {cap} bytes")
        return target.read_bytes()

    def _check_size(self) -> None:
        if _tree_size(self._need_root()) > self.limits.max_workspace_bytes:
            raise SandboxError("build folder grew past its size limit")


# ---------------------------------------------------------------- environment


def _clean_env(workspace: Path, tool_dirs: list[Path], extra: dict[str, str] | None) -> dict:
    env = {
        "PATH": os.pathsep.join(str(d) for d in tool_dirs),
        "HOME": str(workspace),
        "TMPDIR": str(workspace),
        "TEMP": str(workspace),
        "TMP": str(workspace),
        "LANG": "C",
        "LC_ALL": "C",
    }
    for key in ("http_proxy", "https_proxy", "all_proxy", "ftp_proxy"):
        env[key] = env[key.upper()] = _DEAD_PROXY
    env["no_proxy"] = env["NO_PROXY"] = ""
    if _IS_WIN:
        sysroot = os.environ.get("SystemRoot", r"C:\Windows")
        env["SystemRoot"] = sysroot
        env["PATH"] += os.pathsep + os.path.join(sysroot, "System32")
        env["USERPROFILE"] = str(workspace)
    for key, value in (extra or {}).items():
        if not key.replace("_", "").isalnum() or not key.isupper() or "\0" in value:
            raise SandboxError(f"bad environment entry {key!r}")
        env[key] = value
    return env


def _check_argv(argv: list[str | Path], tool_dirs: list[Path]) -> list[str]:
    if not argv:
        raise SandboxError("nothing to run")
    args = [str(a) for a in argv]
    for a in args:
        if "\0" in a or len(a) > 4096:
            raise SandboxError("bad build argument")
    exe = Path(args[0]).resolve()
    if not exe.is_file() or not any(d in exe.parents for d in tool_dirs):
        raise SandboxError(f"program is not part of a bundled toolchain: {args[0]}")
    args[0] = str(exe)
    return args


# ---------------------------------------------------------------- linux helpers

_SYS_TOOL_DIRS = ("/usr/bin", "/bin")


def _system_tool(name: str) -> str | None:
    for d in _SYS_TOOL_DIRS:
        p = os.path.join(d, name)
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return None


@lru_cache(maxsize=1)
def _netns_prefix() -> tuple[str, ...]:
    """``unshare`` prefix for an empty network namespace, or () if the OS blocks it
    (e.g. Ubuntu 24.04+ restricts unprivileged user namespaces through AppArmor)."""
    if _IS_WIN or not sys.platform.startswith("linux"):
        return ()
    unshare = _system_tool("unshare")
    if not unshare:
        return ()
    prefix = (unshare, "--user", "--map-root-user", "--net", "--")
    true = _system_tool("true") or "/bin/true"
    try:
        probe = subprocess.run(  # noqa: S603
            [*prefix, true], capture_output=True, timeout=5, env={"PATH": ""}, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return ()
    return prefix if probe.returncode == 0 else ()


def _rlimit_prefix(limits: BuildLimits) -> tuple[str, ...]:
    prlimit = _system_tool("prlimit")
    if _IS_WIN or not prlimit:
        return ()
    cpu = int(limits.timeout_s) + 5
    return (
        prlimit,
        f"--cpu={cpu}",
        f"--as={limits.memory_bytes}",
        f"--fsize={limits.max_file_bytes}",
        "--core=0",
        "--",
    )


def _post_spawn_rlimits(pid: int, limits: BuildLimits) -> None:
    """Fallback when the prlimit tool is missing (small race, still bounded by timeout)."""
    try:
        import resource

        cpu = int(limits.timeout_s) + 5
        for res, val in (
            (resource.RLIMIT_CPU, cpu),
            (resource.RLIMIT_AS, limits.memory_bytes),
            (resource.RLIMIT_FSIZE, limits.max_file_bytes),
            (resource.RLIMIT_CORE, 0),
        ):
            resource.prlimit(pid, res, (val, val))
    except (ImportError, OSError, ValueError, AttributeError):
        pass


# ---------------------------------------------------------------- windows job object


class _WinJob:
    """Kill-on-close Job Object with memory and process-count limits."""

    def __init__(self, limits: BuildLimits) -> None:
        import ctypes
        from ctypes import wintypes

        class IoCounters(ctypes.Structure):
            _fields_ = [
                (n, ctypes.c_ulonglong)
                for n in (
                    "ReadOperationCount",
                    "WriteOperationCount",
                    "OtherOperationCount",
                    "ReadTransferCount",
                    "WriteTransferCount",
                    "OtherTransferCount",
                )
            ]

        class Basic(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class Extended(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", Basic),
                ("IoInfo", IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        self._k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._k32.CreateJobObjectW.restype = wintypes.HANDLE
        self._k32.OpenProcess.restype = wintypes.HANDLE
        self.handle = self._k32.CreateJobObjectW(None, None)
        if not self.handle:
            raise SandboxError("could not create a Windows job object")
        info = Extended()
        info.BasicLimitInformation.LimitFlags = (
            0x2000  # KILL_ON_JOB_CLOSE
            | 0x0200  # JOB_MEMORY
            | 0x0008  # ACTIVE_PROCESS
            | 0x0400  # DIE_ON_UNHANDLED_EXCEPTION
        )
        info.BasicLimitInformation.ActiveProcessLimit = limits.max_processes
        info.JobMemoryLimit = limits.memory_bytes
        if not self._k32.SetInformationJobObject(
            wintypes.HANDLE(self.handle), 9, ctypes.byref(info), ctypes.sizeof(info)
        ):
            self.close()
            raise SandboxError("could not set Windows job limits")

    def assign(self, pid: int) -> None:
        from ctypes import wintypes

        proc = self._k32.OpenProcess(0x0001 | 0x0100, False, pid)  # TERMINATE | SET_QUOTA
        if not proc:
            raise SandboxError("could not open build process")
        try:
            if not self._k32.AssignProcessToJobObject(
                wintypes.HANDLE(self.handle), wintypes.HANDLE(proc)
            ):
                raise SandboxError("could not limit build process")
        finally:
            self._k32.CloseHandle(wintypes.HANDLE(proc))

    def kill(self) -> None:
        from ctypes import wintypes

        if self.handle:
            self._k32.TerminateJobObject(wintypes.HANDLE(self.handle), 1)

    def close(self) -> None:
        from ctypes import wintypes

        if self.handle:
            self._k32.CloseHandle(wintypes.HANDLE(self.handle))
            self.handle = None


# ---------------------------------------------------------------- run


def _read_capped(fh, cap: int) -> str:
    fh.seek(0)
    data = fh.read(cap + 1)
    text = data[:cap].decode("utf-8", errors="replace")
    return text + ("\n[output trimmed]" if len(data) > cap else "")


def _kill_tree(proc: subprocess.Popen, job: _WinJob | None) -> None:
    try:
        if job is not None:
            job.kill()
        else:
            os.killpg(proc.pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        pass
    try:
        proc.kill()
    except OSError:
        pass


def run_build(
    argv: list[str | Path],
    *,
    workspace: BuildWorkspace,
    toolchain_dirs: list[str | Path],
    limits: BuildLimits | None = None,
    extra_env: dict[str, str] | None = None,
) -> BuildResult:
    """Run one toolchain program inside ``workspace`` under the sandbox rules above."""
    limits = limits or workspace.limits
    root = workspace._need_root()
    tool_dirs = [Path(d).resolve() for d in toolchain_dirs]
    args = _check_argv(argv, tool_dirs)
    env = _clean_env(root, tool_dirs, extra_env)
    netns = _netns_prefix()
    rlim = _rlimit_prefix(limits)
    full = [*netns, *rlim, *args]

    kwargs: dict = {}
    job: _WinJob | None = None
    if _IS_WIN:
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        job = _WinJob(limits)
    else:
        kwargs["start_new_session"] = True

    start = time.monotonic()
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        try:
            proc = subprocess.Popen(  # noqa: S603 - validated argument list, no shell
                full,
                cwd=root,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=err,
                shell=False,
                close_fds=True,
                **kwargs,
            )
        except OSError as exc:
            if job:
                job.close()
            raise SandboxError(f"could not start build tool: {exc}") from exc
        try:
            if job is not None:
                job.assign(proc.pid)
            elif not rlim:
                _post_spawn_rlimits(proc.pid, limits)
            try:
                code = proc.wait(timeout=limits.timeout_s)
            except subprocess.TimeoutExpired:
                _kill_tree(proc, job)
                proc.wait()
                raise SandboxError("the build took too long and was stopped") from None
        except BaseException:
            if proc.poll() is None:
                _kill_tree(proc, job)
                proc.wait()
            raise
        finally:
            if job is not None:
                job.close()  # kills anything the tool left running
            elif proc.returncode is not None:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except (OSError, ProcessLookupError):
                    pass
        result = BuildResult(
            returncode=code,
            stdout=_read_capped(out, limits.max_output_bytes),
            stderr=_read_capped(err, limits.max_output_bytes),
            seconds=round(time.monotonic() - start, 3),
            network_isolated=bool(netns),
        )
    workspace._check_size()
    return result
