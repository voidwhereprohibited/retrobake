"""Regenerate the hash-pinned CI requirement files in requirements/.

Resolves each input set with pip for every CI target (Linux and Windows, Python 3.12 and
3.13, wheels only), then writes every pinned release with the sha256 of all of its PyPI
files, so `pip install --require-hashes` works on every runner. Refuses yanked releases.

    python tools/lock_requirements.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "requirements"
RUNTIME = ["PySide6>=6.8", "fastjsonschema>=2.21.2", "setuptools>=75", "wheel"]
SETS = {
    "lint": ["ruff>=0.17"],
    "runtime": RUNTIME,
    "dev": [*RUNTIME, "pytest>=9", "ruff>=0.17", "pip-audit>=2.10"],
}
LINUX_TAGS = [f"manylinux_2_{n}_x86_64" for n in range(39, 16, -1)]
LINUX_TAGS += ["manylinux2014_x86_64", "manylinux2010_x86_64", "manylinux1_x86_64"]
PLATFORMS = {"linux": LINUX_TAGS, "win32": ["win_amd64"]}
PYTHONS = ["3.12", "3.13"]
# pip evaluates environment markers against the interpreter running this script, not the
# --platform/--python-version targets, so conditional deps that apply to a CI target are
# added here explicitly. check_markers() fails if a new one appears that is not listed.
MARKER_DEPS = {
    "dev": [
        ("colorama", 'sys_platform == "win32"'),
        ("typing-extensions", 'python_version < "3.13"'),
    ],
}


def resolve(reqs: list[str], plat: list[str], py: str) -> dict[str, str]:
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "r.json"
        abi = "cp" + py.replace(".", "")
        cmd = [sys.executable, "-m", "pip", "install", "-q", "--dry-run", "--ignore-installed"]
        cmd += ["--only-binary", ":all:", "--python-version", py]
        cmd += [arg for tag in plat for arg in ("--platform", tag)]
        cmd += ["--implementation", "cp", "--abi", abi, "--abi", "abi3", "--abi", "none"]
        cmd += ["--report", str(report), *reqs]
        subprocess.run(cmd, check=True)  # noqa: S603 - fixed argv, no shell
        data = json.loads(report.read_text())
    return {i["metadata"]["name"].lower(): i["metadata"]["version"] for i in data["install"]}


def pypi_hashes(name: str, version: str) -> list[str]:
    url = f"https://pypi.org/pypi/{name}/{version}/json"
    with urllib.request.urlopen(url, timeout=60) as resp:  # noqa: S310 - fixed https URL
        files = json.load(resp)["urls"]
    if any(f.get("yanked") for f in files):
        raise SystemExit(f"{name}=={version} is yanked; pick another version")
    return sorted({f["digests"]["sha256"] for f in files})


def pypi_info(name: str, version: str = "") -> dict:
    url = f"https://pypi.org/pypi/{name}/{version + '/' if version else ''}json"
    with urllib.request.urlopen(url, timeout=60) as resp:  # noqa: S310 - fixed https URL
        return json.load(resp)


def check_markers(pins: set[str], name: str) -> None:
    """Fail if a pinned package has a conditional dep that a CI target needs but is unpinned."""
    from packaging.markers import Marker
    from packaging.requirements import Requirement

    envs = [
        {
            "sys_platform": p,
            "platform_system": "Windows" if p == "win32" else "Linux",
            "os_name": "nt" if p == "win32" else "posix",
            "python_version": v,
            "python_full_version": v + ".0",
            "implementation_name": "cpython",
            "platform_python_implementation": "CPython",
            "platform_machine": "x86_64",
        }
        for p in PLATFORMS
        for v in PYTHONS
    ]
    for pkg, ver in sorted(p.split("==") for p in pins):
        for spec in pypi_info(pkg, ver)["info"].get("requires_dist") or []:
            req = Requirement(spec)
            if req.marker is None or "extra" in str(req.marker):
                continue
            dep = req.name.lower().replace("_", "-")
            needed = any(Marker(str(req.marker)).evaluate(env) for env in envs)
            if needed and dep not in {q.split("==")[0].replace("_", "-") for q in pins}:
                raise SystemExit(f"{name}: {pkg} needs {spec!r} on a CI target; add to MARKER_DEPS")


def marker(targets: set[tuple[str, str]]) -> str:
    plats = {p for p, _ in targets}
    pys = {v for _, v in targets}
    if len(targets) == len(PLATFORMS) * len(PYTHONS):
        return ""
    parts = []
    if plats != set(PLATFORMS) and len(targets) == len(plats) * len(pys):
        parts.append(" or ".join(f'sys_platform == "{p}"' for p in sorted(plats)))
    if pys != set(PYTHONS) and len(targets) == len(plats) * len(pys):
        parts.append(" or ".join(f'python_version == "{v}"' for v in sorted(pys)))
    if len(targets) != len(plats) * len(pys):
        clauses = [f'(sys_platform == "{p}" and python_version == "{v}")' for p, v in targets]
        parts = [" or ".join(sorted(clauses))]
    return " ; " + " and ".join(f"({p})" if " or " in p else p for p in parts)


def lock(name: str, reqs: list[str]) -> None:
    seen: dict[tuple[str, str], set[tuple[str, str]]] = {}
    for plat_key, plat in PLATFORMS.items():
        for py in PYTHONS:
            for pkg, ver in resolve(reqs, plat, py).items():
                seen.setdefault((pkg, ver), set()).add((plat_key, py))
    entries = [(pkg, ver, marker(t)) for (pkg, ver), t in sorted(seen.items())]
    for dep, mark in MARKER_DEPS.get(name, []):
        entries.append((dep, pypi_info(dep)["info"]["version"], f" ; {mark}"))
    check_markers({f"{p.lower()}=={v}" for p, v, _ in entries}, name)
    lines = [
        f"# Hash-pinned by tools/lock_requirements.py from: {' '.join(reqs)}",
        "# Install with: python -m pip install --require-hashes -r requirements/" + name + ".txt",
    ]
    for pkg, ver, mark in sorted(entries):
        hashes = pypi_hashes(pkg, ver)
        lines.append(f"{pkg}=={ver}{mark} \\")
        lines += [f"    --hash=sha256:{h} \\" for h in hashes[:-1]]
        lines.append(f"    --hash=sha256:{hashes[-1]}")
    OUT.mkdir(exist_ok=True)
    (OUT / f"{name}.txt").write_text("\n".join(lines) + "\n")
    print(f"requirements/{name}.txt: {len(entries)} pins")


if __name__ == "__main__":
    for set_name, set_reqs in SETS.items():
        lock(set_name, set_reqs)
