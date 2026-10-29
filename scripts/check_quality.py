"""Run the quality gates: tests with coverage, mypy and ruff (Definition of done (h) in CLAUDE.md).

Gates:
    pytest --cov=cmsopen --cov-fail-under=90   (branch coverage of src/cmsopen, from genuine tests)
    mypy src                                   (disallow_untyped_defs, warn_unused_ignores; see pyproject.toml)
    ruff check src tests scripts examples

Each tool's output is printed, then one line per gate, then "OK: quality gates pass" (exit 0) or
"FAIL: ..." naming the failed gates (exit 1).

Usage:
    python scripts/check_quality.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GATES = (
    ("pytest with coverage >= 90 %", [sys.executable, "-m", "pytest", "-q", "--cov=cmsopen", "--cov-report=term",
                                      "--cov-fail-under=90"]),
    ("mypy", [sys.executable, "-m", "mypy", "src"]),
    ("ruff", [sys.executable, "-m", "ruff", "check", "src", "tests", "scripts", "examples"]),
)


def main() -> int:
    """Run every gate from the repository root, print the outputs and the verdict, return the exit status."""
    failed = []
    results = []
    for name, cmd in GATES:
        print(f"=== {name}: {' '.join(Path(c).name if i == 0 else c for i, c in enumerate(cmd))}", flush=True)
        out = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
        print(out.stdout.rstrip())
        if out.stderr.strip():
            print(out.stderr.rstrip())
        ok = out.returncode == 0
        results.append((name, ok))
        if not ok:
            failed.append(name)
    print("=== summary")
    for name, ok in results:
        print(f"  {'OK  ' if ok else 'FAIL'} {name}")
    if failed:
        print(f"FAIL: quality gates failed: {', '.join(failed)}")
        return 1
    print("OK: quality gates pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
