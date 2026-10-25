"""Fail if any GitHub Actions `uses:` line is not pinned to a full commit SHA.

Every third-party action must look like:
    uses: owner/repo@<40-hex-sha> # vX.Y.Z
Local actions (uses: ./...) are allowed. Dependabot keeps the SHA and comment in sync.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PINNED = re.compile(r"uses:\s*[\w.-]+/[\w./-]+@[0-9a-f]{40} # v\d+\.\d+\.\d+\s*$")
LOCAL = re.compile(r"uses:\s*\./")


def main() -> int:
    root = Path(__file__).resolve().parent.parent / ".github"
    bad = []
    for path in sorted(root.rglob("*.y*ml")):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "uses:" not in line or line.lstrip().startswith("#"):
                continue
            if not (PINNED.search(line) or LOCAL.search(line)):
                bad.append(f"{path.relative_to(root.parent)}:{n}: {line.strip()}")
    if bad:
        print("Unpinned GitHub Actions (pin to a full commit SHA + '# vX.Y.Z'):")
        print("\n".join(bad))
        return 1
    print("All GitHub Actions are pinned to commit SHAs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
