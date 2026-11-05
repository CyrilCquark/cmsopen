"""Record the 1,000-toy pull tests' printed values in dev/test_metrics.json, for scripts/production_extras.py.

The values come from running the tests in tests/test_fitting*.py (or from a saved pytest log, with --from-log). They are
toy results from the test suite, not production data. The record names the blob of src/cmsopen/fitting.py it belongs to,
so a later change of the fit code makes it stale, and production_extras.py then says so.

Usage:
    python scripts/record_test_metrics.py [--from-log FILE]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "dev" / "test_metrics.json"
TESTS = ("tests/test_fitting.py", "tests/test_fitting_cb.py", "tests/test_fitting_cb2.py", "tests/test_fitting_cb3.py")
_LINE = re.compile(r"^\s*(?P<name>.*?)pull test, 1,000 toys[,:]\s*(?P<rest>.*)$", flags=re.M)


def parse(text: str) -> list[dict]:
    """One entry per toy test: its failed-fit count and each parameter's pull mean and standard deviation."""
    out = []
    for match in _LINE.finditer(text):
        rest = match.group("rest")
        failed = re.search(r"(\d+) failed fits", rest)
        params = {
            name: {"mean": float(m), "std": float(s)}
            for name, m, s in re.findall(r"(\w+) mean ([-+]\d+\.\d+) std (\d+\.\d+)", rest)
        }
        if not params:  # "mean +0.103, std 0.997": the peak position only
            single = re.search(r"mean ([-+]\d+\.\d+), std (\d+\.\d+)", rest)
            if single:
                params = {"mean": {"mean": float(single.group(1)), "std": float(single.group(2))}}
        out.append(
            {
                "test": match.group("name").strip() or "gauss_poly",
                "n_toys": 1000,
                "n_failed": int(failed.group(1)) if failed else 0,
                "pulls": params,
            }
        )
    return out


def main(argv: list[str] | None = None) -> int:
    """Run or read the toy tests and write the record; fail if no test printed its values."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--from-log", type=Path, default=None, help="a saved pytest log instead of running the tests")
    args = parser.parse_args(argv)
    if args.from_log:
        text = args.from_log.read_text()
    else:
        run = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                *TESTS,
                "-k",
                "test_pull_test_1000_toys",
                "--timeout=1200",
            ],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        if run.returncode != 0:
            print(run.stdout[-2000:])
            print("FAIL: the toy tests did not pass; nothing recorded")
            return 1
        text = run.stdout
    entries = parse(text)
    if not entries:
        print("FAIL: no toy test printed its values")
        return 1
    blob = subprocess.run(
        ["git", "rev-parse", "HEAD:src/cmsopen/fitting.py"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.strip()
    record = {"label": "from the test suite, not production data", "fitting_blob": blob, "tests": entries}
    OUT.write_text(json.dumps(record, indent=2) + "\n")
    print(f"recorded {len(entries)} toy tests in {OUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
