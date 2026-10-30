"""Run the full test suite and the quality gates at HEAD and record the result for the production preflight.

Requires a clean working tree, so that the record describes exactly the
committed state. Writes build/gates/<HEAD>.json with the HEAD commit, the exit
statuses of ``pytest`` (the full suite) and ``scripts/check_quality.py``,
pytest's summary line and the total line coverage of src/cmsopen.
``scripts/production_preflight.py`` accepts only a record whose HEAD is the
current HEAD and whose two statuses are 0.

Usage:
    python scripts/run_gates.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def main() -> int:
    """Run the gates and write the record; return 0 only if both passed."""
    status = subprocess.run(["git", "status", "--porcelain"], cwd=REPO, capture_output=True, text=True)
    # the state of a production attempt that failed after the lock (scripts/production_run.py) is not a change
    run_state = ("results/production_run.lock", "results/production_run.log")
    dirty = [line for line in status.stdout.splitlines() if line.strip() and line[3:] not in run_state]
    if status.returncode != 0 or dirty:
        print("FAIL: the working tree is not clean; commit first so the record describes HEAD")
        return 1
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip()
    start = time.time()
    pytest = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=REPO,
                            capture_output=True, text=True)
    summary = next((line for line in reversed(pytest.stdout.splitlines()) if " passed" in line or " failed" in line),
                   "no summary line")
    print(f"pytest: exit {pytest.returncode}; {summary}")
    quality = subprocess.run([sys.executable, str(REPO / "scripts" / "check_quality.py")], cwd=REPO,
                             capture_output=True, text=True)
    print(f"check_quality: exit {quality.returncode}; {quality.stdout.strip().splitlines()[-1:]}")
    total = next((line.split()[-1] for line in quality.stdout.splitlines() if line.startswith("TOTAL ")), "unknown")
    record = {"head": head, "pytest_rc": pytest.returncode, "quality_rc": quality.returncode, "summary": summary,
              "coverage_total": total, "seconds": round(time.time() - start)}
    out = REPO / "build" / "gates" / f"{head}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2) + "\n")
    print(f"recorded in {out.relative_to(REPO)}")
    return 0 if pytest.returncode == 0 and quality.returncode == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
